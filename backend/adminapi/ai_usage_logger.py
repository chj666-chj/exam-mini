"""AI 使用日志记录与聚合分析。

记录每次 AI 功能调用的元数据（功能名、用户、状态、Token 用量、耗时等），
存储在 ai_usage_logs collection（core.Document），供管理后台「AI 使用分析」看板聚合展示。

日志结构：
{
    func_name: str,          # AI 功能标识（如 question_analyze / kb_qa）
    func_label: str,         # 功能中文名
    source: str,             # 'admin'（管理端）或 'mp'（小程序端）
    openid: str,             # 用户 openid（小程序端调用时）
    admin_user: str,         # 管理员用户名（管理端调用时）
    status: str,             # 'success' / 'failed' / 'pending'
    model: str,              # 使用的模型名
    tokens_prompt: int,      # 输入 Token 数
    tokens_completion: int,  # 输出 Token 数
    tokens_total: int,       # 总 Token 数
    duration_ms: int,        # 调用耗时（毫秒）
    error: str,              # 失败原因（成功时为空）
    job_id: str,             # 异步任务 ID（异步调用时）
    created_at: str,         # ISO 时间戳
}
"""
import logging
import uuid
from collections import Counter, defaultdict
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import Document

logger = logging.getLogger(__name__)

_AI_USAGE_COLLECTION = 'ai_usage_logs'

# ---- AI 功能清单（功能标识 → 中文名 + 说明 + 端 + 权限）----
AI_FEATURE_CATALOG = [
    {
        'func_name': 'ai_assist',
        'label': 'AI 辅助写作',
        'description': '根据主题/关键词生成 Markdown 格式备考文章',
        'source': 'mp',
        'perm': 'ai.config',
        'tier': 'standard',
    },
    {
        'func_name': 'question_analyze',
        'label': 'AI 题目解析',
        'description': '对单题/批量题目生成 AI 解析（知识点、解题思路、答案分析）',
        'source': 'admin',
        'perm': 'ai.analyze',
        'tier': 'standard',
    },
    {
        'func_name': 'exam_compose',
        'label': 'AI 智能组卷',
        'description': '基于题型/难度/知识点分布自动组卷（经典模式）',
        'source': 'admin',
        'perm': 'ai.compose',
        'tier': 'complex',
    },
    {
        'func_name': 'smart_compose',
        'label': 'AI 智能组卷 V2',
        'description': '三阶段定向组卷：知识点掌握度分析→考试蓝图→KP索引检索',
        'source': 'admin',
        'perm': 'ai.compose',
        'tier': 'complex',
    },
    {
        'func_name': 'ai_grade',
        'label': 'AI 智能判卷',
        'description': '对主观题答案进行 AI 批量判卷，生成评分与反馈',
        'source': 'admin',
        'perm': 'ai.grade',
        'tier': 'complex',
    },
    {
        'func_name': 'exam_analyze',
        'label': 'AI 试卷分析',
        'description': '聚合试卷答题数据，生成难度/区分度/知识点掌握分析报告',
        'source': 'admin',
        'perm': 'ai.report',
        'tier': 'complex',
    },
    {
        'func_name': 'review_recommend',
        'label': '复习推荐',
        'description': '基于用户答题历史生成今日复习计划（每日1次）',
        'source': 'mp',
        'perm': '-',
        'tier': 'lite',
    },
    {
        'func_name': 'learning_profile',
        'label': '答题分析（学习画像）',
        'description': '分析用户答题历史生成学习画像报告（每7天1次）',
        'source': 'mp',
        'perm': '-',
        'tier': 'complex',
    },
    {
        'func_name': 'kb_qa',
        'label': '知识库 RAG 问答',
        'description': '基于知识库检索增强生成回答用户提问（每日20次）',
        'source': 'mp',
        'perm': '-',
        'tier': 'standard',
    },
    {
        'func_name': 'auto_tag',
        'label': 'AI 自动标签',
        'description': 'AI 推荐题目标签并自动同步到标签管理、绑定到题目',
        'source': 'admin',
        'perm': 'ai.analyze',
        'tier': 'standard',
    },
    {
        'func_name': 'excel_validate',
        'label': 'AI 数据校验',
        'description': 'Excel 导入前 AI 智能校验题目数据格式与内容',
        'source': 'admin',
        'perm': 'question.import',
        'tier': 'complex',
    },
    {
        'func_name': 'learning_report',
        'label': '学习报告',
        'description': '生成周报/月报学习报告，含学习进度与趋势分析',
        'source': 'mp',
        'perm': '-',
        'tier': 'complex',
    },
    {
        'func_name': 'cs_chat',
        'label': '智能客服',
        'description': 'AI 客服对话，解答用户常见问题（每日30次）',
        'source': 'mp',
        'perm': '-',
        'tier': 'standard',
    },
    {
        'func_name': 'article_enhance',
        'label': '文章增强',
        'description': '对已有文章进行润色、续写、改写等增强操作',
        'source': 'mp',
        'perm': '-',
        'tier': 'standard',
    },
]

# 按功能标识索引，便于快速查找
_FEATURE_MAP = {f['func_name']: f for f in AI_FEATURE_CATALOG}


def get_feature_label(func_name):
    """根据 func_name 获取功能中文名，未注册时返回 func_name 本身。"""
    return _FEATURE_MAP.get(func_name, {}).get('label', func_name)


class AIUsageLogger:
    """AI 使用日志记录器。

    所有方法均为静态方法，可直接调用，无需实例化。
    日志写入使用 Document.objects.create()，与项目通用文档存储模式一致。
    """

    COLLECTION = _AI_USAGE_COLLECTION
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_PENDING = 'pending'

    @classmethod
    def log(cls, func_name, source='admin', openid='', admin_user='',
            status='success', model='', tokens_prompt=0, tokens_completion=0,
            tokens_total=0, duration_ms=0, error='', job_id=''):
        """记录一条 AI 使用日志。

        Args:
            func_name: AI 功能标识（如 'question_analyze'）
            source: 调用来源，'admin' 或 'mp'
            openid: 用户 openid（小程序端调用时）
            admin_user: 管理员用户名（管理端调用时）
            status: 调用状态 'success' / 'failed' / 'pending'
            model: 使用的模型名
            tokens_prompt: 输入 Token 数
            tokens_completion: 输出 Token 数
            tokens_total: 总 Token 数
            duration_ms: 调用耗时（毫秒）
            error: 失败原因
            job_id: 异步任务 ID
        """
        try:
            doc_id = uuid.uuid4().hex[:20]
            Document.objects.create(
                collection=cls.COLLECTION,
                doc_id=doc_id,
                data={
                    'func_name': func_name,
                    'func_label': get_feature_label(func_name),
                    'source': source,
                    'openid': openid or '',
                    'admin_user': admin_user or '',
                    'status': status,
                    'model': model or '',
                    'tokens_prompt': int(tokens_prompt or 0),
                    'tokens_completion': int(tokens_completion or 0),
                    'tokens_total': int(tokens_total or 0),
                    'duration_ms': int(duration_ms or 0),
                    'error': (error or '')[:500],
                    'job_id': job_id or '',
                    'created_at': timezone.now().isoformat(),
                },
            )
        except Exception as e:
            # 日志记录失败不应影响业务流程
            logger.warning('AIUsageLogger.log failed: %s', e)

    @classmethod
    def _iter_logs(cls):
        """惰性遍历所有使用日志。"""
        for item in Document.objects.filter(collection=cls.COLLECTION).values_list(
                'data', flat=True):
            yield item

    @classmethod
    def _parse_date(cls, iso_str):
        """解析 ISO 时间字符串为 date 对象，失败返回 None。"""
        if not iso_str:
            return None
        try:
            dt = parse_datetime(iso_str)
            if dt:
                return dt.date()
        except (ValueError, TypeError):
            pass
        return None

    @classmethod
    def _anchor_date(cls):
        """取日志中最晚的日期作为基准日，缺省为今天。"""
        latest = None
        for log in cls._iter_logs():
            d = cls._parse_date(log.get('created_at'))
            if d and (latest is None or d > latest):
                latest = d
        return latest or timezone.localdate()

    @classmethod
    def overview(cls, days=30):
        """AI 使用概览（KPI 卡片数据）。

        返回：
            total_calls: 总调用次数
            total_tokens: 总 Token 消耗
            success_rate: 成功率（0-1）
            active_users: 活跃用户数（去重 openid + admin_user）
            active_features: 活跃功能数
            failed_calls: 失败次数
            avg_duration_ms: 平均耗时
            by_source: {admin: N, mp: N}
            base_date: 基准日
        """
        anchor = cls._anchor_date()
        start = anchor - timedelta(days=days - 1)

        total_calls = 0
        total_tokens = 0
        success_count = 0
        failed_count = 0
        total_duration = 0
        duration_count = 0
        users = set()
        func_set = set()
        source_counter = Counter()

        for log in cls._iter_logs():
            d = cls._parse_date(log.get('created_at'))
            if not d or d < start or d > anchor:
                continue
            total_calls += 1
            total_tokens += int(log.get('tokens_total', 0) or 0)
            status = log.get('status', '')
            if status == cls.STATUS_SUCCESS:
                success_count += 1
            elif status == cls.STATUS_FAILED:
                failed_count += 1
            dur = int(log.get('duration_ms', 0) or 0)
            if dur > 0:
                total_duration += dur
                duration_count += 1
            # 用户去重
            openid = log.get('openid', '')
            admin_user = log.get('admin_user', '')
            if openid:
                users.add('mp:' + openid)
            if admin_user:
                users.add('admin:' + admin_user)
            func_set.add(log.get('func_name', ''))
            source_counter[log.get('source', '')] += 1

        return {
            'total_calls': total_calls,
            'total_tokens': total_tokens,
            'success_rate': round(success_count / total_calls, 4) if total_calls else 0,
            'active_users': len(users),
            'active_features': len(func_set),
            'failed_calls': failed_count,
            'avg_duration_ms': round(total_duration / duration_count) if duration_count else 0,
            'by_source': {
                'admin': source_counter.get('admin', 0),
                'mp': source_counter.get('mp', 0),
            },
            'base_date': anchor.strftime('%Y-%m-%d'),
            'days': days,
        }

    @classmethod
    def trend(cls, days=30):
        """AI 调用时间趋势（按天聚合）。

        返回 {base_date, days, series: [{date, calls, tokens, success, failed, active_users}]}
        """
        anchor = cls._anchor_date()
        start = anchor - timedelta(days=days - 1)

        # 按天聚合
        day_data = defaultdict(lambda: {
            'calls': 0, 'tokens': 0, 'success': 0, 'failed': 0, 'users': set()
        })

        for log in cls._iter_logs():
            d = cls._parse_date(log.get('created_at'))
            if not d or d < start or d > anchor:
                continue
            key = d.isoformat()
            bucket = day_data[key]
            bucket['calls'] += 1
            bucket['tokens'] += int(log.get('tokens_total', 0) or 0)
            status = log.get('status', '')
            if status == cls.STATUS_SUCCESS:
                bucket['success'] += 1
            elif status == cls.STATUS_FAILED:
                bucket['failed'] += 1
            openid = log.get('openid', '')
            admin_user = log.get('admin_user', '')
            if openid:
                bucket['users'].add('mp:' + openid)
            if admin_user:
                bucket['users'].add('admin:' + admin_user)

        series = []
        for offset in range(days - 1, -1, -1):
            day = anchor - timedelta(days=offset)
            key = day.isoformat()
            bucket = day_data.get(key, {'calls': 0, 'tokens': 0, 'success': 0,
                                        'failed': 0, 'users': set()})
            series.append({
                'date': day.strftime('%Y-%m-%d'),
                'calls': bucket['calls'],
                'tokens': bucket['tokens'],
                'success': bucket['success'],
                'failed': bucket['failed'],
                'active_users': len(bucket['users']),
            })

        return {'base_date': anchor.strftime('%Y-%m-%d'), 'days': days, 'series': series}

    @classmethod
    def by_function(cls, days=30):
        """按 AI 功能维度汇总。

        返回 {list: [{func_name, func_label, calls, success, failed, tokens, avg_duration, active_users}], total}
        """
        anchor = cls._anchor_date()
        start = anchor - timedelta(days=days - 1)

        func_data = defaultdict(lambda: {
            'calls': 0, 'success': 0, 'failed': 0,
            'tokens': 0, 'total_duration': 0, 'duration_count': 0,
            'users': set(),
        })

        for log in cls._iter_logs():
            d = cls._parse_date(log.get('created_at'))
            if not d or d < start or d > anchor:
                continue
            fname = log.get('func_name', 'unknown')
            bucket = func_data[fname]
            bucket['calls'] += 1
            bucket['tokens'] += int(log.get('tokens_total', 0) or 0)
            status = log.get('status', '')
            if status == cls.STATUS_SUCCESS:
                bucket['success'] += 1
            elif status == cls.STATUS_FAILED:
                bucket['failed'] += 1
            dur = int(log.get('duration_ms', 0) or 0)
            if dur > 0:
                bucket['total_duration'] += dur
                bucket['duration_count'] += 1
            openid = log.get('openid', '')
            admin_user = log.get('admin_user', '')
            if openid:
                bucket['users'].add('mp:' + openid)
            if admin_user:
                bucket['users'].add('admin:' + admin_user)

        result = []
        for fname, bucket in func_data.items():
            result.append({
                'func_name': fname,
                'func_label': get_feature_label(fname),
                'calls': bucket['calls'],
                'success': bucket['success'],
                'failed': bucket['failed'],
                'success_rate': round(bucket['success'] / bucket['calls'], 4) if bucket['calls'] else 0,
                'tokens': bucket['tokens'],
                'avg_duration_ms': round(bucket['total_duration'] / bucket['duration_count']) if bucket['duration_count'] else 0,
                'active_users': len(bucket['users']),
            })

        # 按调用次数降序
        result.sort(key=lambda x: -x['calls'])
        return {'list': result, 'total': len(result)}

    @classmethod
    def by_user(cls, days=30, top_n=20):
        """按用户维度汇总（Token 消耗 + 调用次数 Top N）。

        返回 {list: [{user_key, openid, admin_user, calls, tokens, success, failed, last_active}], total}
        """
        anchor = cls._anchor_date()
        start = anchor - timedelta(days=days - 1)

        user_data = defaultdict(lambda: {
            'calls': 0, 'tokens': 0, 'success': 0, 'failed': 0,
            'last_active': None, 'openid': '', 'admin_user': '',
        })

        for log in cls._iter_logs():
            d = cls._parse_date(log.get('created_at'))
            if not d or d < start or d > anchor:
                continue
            openid = log.get('openid', '')
            admin_user = log.get('admin_user', '')
            if openid:
                user_key = 'mp:' + openid
                user_data[user_key]['openid'] = openid
            elif admin_user:
                user_key = 'admin:' + admin_user
                user_data[user_key]['admin_user'] = admin_user
            else:
                continue

            bucket = user_data[user_key]
            bucket['calls'] += 1
            bucket['tokens'] += int(log.get('tokens_total', 0) or 0)
            status = log.get('status', '')
            if status == cls.STATUS_SUCCESS:
                bucket['success'] += 1
            elif status == cls.STATUS_FAILED:
                bucket['failed'] += 1
            if d and (bucket['last_active'] is None or d.isoformat() > bucket['last_active']):
                bucket['last_active'] = d.isoformat()

        result = []
        for user_key, bucket in user_data.items():
            result.append({
                'user_key': user_key,
                'openid': bucket['openid'],
                'admin_user': bucket['admin_user'],
                'calls': bucket['calls'],
                'tokens': bucket['tokens'],
                'success': bucket['success'],
                'failed': bucket['failed'],
                'last_active': bucket['last_active'] or '',
            })

        # 按 Token 降序
        result.sort(key=lambda x: -x['tokens'])
        return {'list': result[:top_n], 'total': len(user_data)}

    @classmethod
    def function_trend(cls, days=30):
        """按功能分类的调用次数时间趋势（用于堆叠图/多线图）。

        返回 {dates: [str], functions: {func_name: [count_per_day]}}
        """
        anchor = cls._anchor_date()
        start = anchor - timedelta(days=days - 1)

        # 收集所有功能名
        func_names = set()
        day_func_counts = defaultdict(Counter)  # date -> {func_name: count}

        for log in cls._iter_logs():
            d = cls._parse_date(log.get('created_at'))
            if not d or d < start or d > anchor:
                continue
            fname = log.get('func_name', 'unknown')
            func_names.add(fname)
            day_func_counts[d.isoformat()][fname] += 1

        dates = []
        for offset in range(days - 1, -1, -1):
            day = anchor - timedelta(days=offset)
            dates.append(day.strftime('%Y-%m-%d'))

        functions = {}
        for fname in sorted(func_names):
            functions[fname] = [
                day_func_counts.get(
                    (anchor - timedelta(days=days - 1 - i)).isoformat(), {}
                ).get(fname, 0)
                for i in range(days)
            ]

        return {
            'dates': dates,
            'functions': functions,
        }

    @classmethod
    def token_by_function(cls, days=30):
        """按功能维度的 Token 消耗分布（用于饼图/柱状图）。

        返回 [{func_name, func_label, tokens, calls}]
        """
        anchor = cls._anchor_date()
        start = anchor - timedelta(days=days - 1)

        func_tokens = defaultdict(lambda: {'tokens': 0, 'calls': 0})

        for log in cls._iter_logs():
            d = cls._parse_date(log.get('created_at'))
            if not d or d < start or d > anchor:
                continue
            fname = log.get('func_name', 'unknown')
            func_tokens[fname]['tokens'] += int(log.get('tokens_total', 0) or 0)
            func_tokens[fname]['calls'] += 1

        result = []
        for fname, bucket in func_tokens.items():
            result.append({
                'func_name': fname,
                'func_label': get_feature_label(fname),
                'tokens': bucket['tokens'],
                'calls': bucket['calls'],
            })

        result.sort(key=lambda x: -x['tokens'])
        return result

    @classmethod
    def features(cls):
        """返回 AI 功能清单（静态目录）。"""
        return AI_FEATURE_CATALOG
