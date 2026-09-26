# -*- coding: utf-8 -*-
"""为各功能模块补齐「可直接验证」的演示数据（幂等，不删除任何既有数据）。

与 ``seed_data.py``（全量清空重建）不同，本命令只补齐缺失项，适合在已有库上
执行，让业务模块与 AI 模块一进入就有可验证的样本。

补齐内容与对应的验证场景：

===========================================  ==========================================
集合                                        验证的功能
===========================================  ==========================================
articles + code                              文章唯一编码 ART-YYYYMMDD-NNNN、入知识库
knowledgebase（含 source=article 条目）      知识库索引、RAG 问答、文章→索引可追溯
historys（items=题目ID数组 + score_arr）     试卷分析(>=10份)、答题分析(>=20条)、学习报告
notes（错题本）                              错题复习推荐（艾宾浩斯调度）
profiles                                    小程序用户/排行榜
===========================================  ==========================================

前置条件：``exam`` 与 ``questions`` 集合已有数据（由 ``python seed_data.py`` 生成）。

用法：
    python manage.py seed_demo_data
    python manage.py seed_demo_data --users 4 --history-per-user 25
    python manage.py seed_demo_data --force        # 已有数据也重建（按 doc_id 覆盖）
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Document
from adminapi.ai_services import KnowledgeRAGService, _question_correct_codes
from adminapi.article_code import backfill_article_codes

DEMO_OPENID_TEMPLATE = 'oDWYj0User%03dabcdef1234567890'
DEMO_NICKNAMES = ['张明', '李芳', '王强', '赵敏', '刘洋', '陈静']
DEMO_CITIES = [('北京', '北京'), ('上海', '上海'), ('广东', '深圳'),
               ('四川', '成都'), ('湖北', '武汉'), ('浙江', '杭州')]


class Command(BaseCommand):
    help = '为各功能模块补齐可直接验证的演示数据（幂等，不删除既有数据）'

    def add_arguments(self, parser):
        parser.add_argument('--users', type=int, default=3,
                            help='生成答题记录的演示用户数（默认 3）')
        parser.add_argument('--history-per-user', type=int, default=22,
                            help='每个用户的答题记录条数，需 >= 20 以验证答题分析（默认 22）')
        parser.add_argument('--notes-per-user', type=int, default=6,
                            help='每个用户的错题条数（默认 6）')
        parser.add_argument('--force', action='store_true',
                            help='忽略已有数量，按目标数量补齐/覆盖')

    # ---- 主流程 ----

    def handle(self, *args, **options):
        users = max(1, options['users'])
        history_target = max(1, options['history_per_user'])
        notes_target = max(1, options['notes_per_user'])
        force = options['force']

        questions = self._load_questions()
        if not questions:
            self.stdout.write(self.style.ERROR(
                '未找到 questions 集合数据，请先执行：python seed_data.py'))
            return

        exams = self._load_exams()
        if not exams:
            self.stdout.write(self.style.ERROR(
                '未找到 exam 集合数据，请先执行：python seed_data.py'))
            return

        self.stdout.write(self.style.MIGRATE_HEADING('== 演示数据补齐 =='))

        self._ensure_profiles(users)
        history_created = self._seed_histories(users, history_target, questions, exams, force)
        notes_created = self._seed_notes(users, notes_target, questions, force)

        code_result = backfill_article_codes()
        linked = self._link_articles_to_kb()

        self._print_summary(history_created, notes_created, code_result, linked)

    # ---- 数据读取 ----

    @staticmethod
    def _load_questions():
        pool = []
        for doc in Document.objects.filter(collection='questions').order_by('pk'):
            data = doc.data or {}
            qid = doc.doc_id or str(doc.pk)
            kp_names = data.get('knowledgePointNames')
            kp_name = ''
            if isinstance(kp_names, list) and kp_names:
                kp_name = str(kp_names[0])
            pool.append({
                'doc_id': qid,
                'qtype': str(data.get('qtype') or data.get('typecode') or 'single'),
                'examid': str(data.get('examid') or ''),
                'kp_name': kp_name,
                'correct_codes': _question_correct_codes(doc) or set(),
                'all_codes': [
                    str(o.get('code')).upper()
                    for o in (data.get('options') or [])
                    if isinstance(o, dict) and o.get('code')
                ],
            })
        return [q for q in pool if q['correct_codes']]

    @staticmethod
    def _load_exams():
        exams = {}
        for doc in Document.objects.filter(collection='exam'):
            data = doc.data or {}
            exams[doc.doc_id or str(doc.pk)] = {
                'name': str(data.get('name') or ''),
                'total_score': float(data.get('totalScore') or 100),
            }
        return exams

    # ---- 生成逻辑 ----

    def _ensure_profiles(self, users):
        created = 0
        for idx in range(users):
            openid = DEMO_OPENID_TEMPLATE % idx
            doc_id = 'profile_%03d' % (idx + 1)
            if Document.objects.filter(collection='profiles', doc_id=doc_id).exists():
                continue
            province, city = DEMO_CITIES[idx % len(DEMO_CITIES)]
            Document.objects.create(collection='profiles', doc_id=doc_id, data={
                'userInfo': {
                    'nickName': DEMO_NICKNAMES[idx % len(DEMO_NICKNAMES)],
                    'gender': 1,
                    'language': 'zh_CN',
                    'city': city,
                    'province': province,
                    'country': '中国',
                    'avatarUrl': '/images/header.png',
                },
                '_openid': openid,
            })
            created += 1
        if created:
            self.stdout.write('  [profiles] 新增 %d 个演示用户档案' % created)

    def _seed_histories(self, users, target, questions, exams, force):
        created = 0
        for idx in range(users):
            openid = DEMO_OPENID_TEMPLATE % idx
            existing = Document.objects.filter(
                collection='historys', data___openid=openid).count()
            if not force and existing >= target:
                self.stdout.write('  [historys] 用户 %d 已有 %d 条，跳过' % (idx + 1, existing))
                continue
            for n in range(existing, target):
                self._create_history(openid, idx, n, questions, exams)
                created += 1
        self.stdout.write('  [historys] 新增 %d 条' % created)
        return created

    def _create_history(self, openid, user_idx, seq, questions, exams):
        count = random.randint(4, 6)
        picked_questions = random.sample(questions, min(count, len(questions)))
        items, score_arr, right = [], [], 0
        for q in picked_questions:
            correct = sorted(q['correct_codes'])
            if random.random() < 0.65:
                answer = correct
            elif q['qtype'] == 'multiple':
                answer = correct[:max(1, len(correct) - 1)] or correct
            else:
                wrong = [c for c in q['all_codes'] if c not in q['correct_codes']]
                answer = [random.choice(wrong)] if wrong else correct
            if answer == correct:
                right += 1
            items.append(q['doc_id'])
            score_arr.append(answer)

        exam_id = picked_questions[0]['examid']
        exam_meta = exams.get(exam_id, {})
        total_q = len(picked_questions)
        total_score = exam_meta.get('total_score', 100)
        doc_id = 'hist_demo%02d_%03d' % (user_idx + 1, seq + 1)

        Document.objects.update_or_create(
            collection='historys', doc_id=doc_id,
            defaults={'data': {
                '_openid': openid,
                'subject': {'_id': exam_id, 'name': exam_meta.get('name', '')},
                'examid': exam_id,
                'time': '%d:%02d' % (random.randint(0, 5), random.randint(10, 59)),
                'items': items,
                'score_arr': score_arr,
                'rightNum': right,
                'nums': total_q,
                'score': round(right / total_q * total_score, 1),
                'total': total_q,
                'createTime': (timezone.now() - timedelta(
                    days=random.randint(0, 25))).strftime('%Y/%m/%d %H:%M'),
            }},
        )

    def _seed_notes(self, users, target, questions, force):
        created = 0
        for idx in range(users):
            openid = DEMO_OPENID_TEMPLATE % idx
            existing = Document.objects.filter(
                collection='notes', data___openid=openid).count()
            if not force and existing >= target:
                self.stdout.write('  [notes] 用户 %d 已有 %d 条，跳过' % (idx + 1, existing))
                continue
            for n in range(existing, target):
                self._create_note(openid, idx, n, questions)
                created += 1
        self.stdout.write('  [notes] 新增 %d 条' % created)
        return created

    def _create_note(self, openid, user_idx, seq, questions):
        q = random.choice(questions)
        wrong_codes = [c for c in q['all_codes'] if c not in q['correct_codes']]
        selected = wrong_codes[0] if wrong_codes else ''
        doc_id = 'note_demo%02d_%03d' % (user_idx + 1, seq + 1)
        Document.objects.update_or_create(
            collection='notes', doc_id=doc_id,
            defaults={'data': {
                '_openid': openid,
                'ordernum': '2026%02d%02d%04d' % (user_idx + 1, seq + 1, random.randint(0, 9999)),
                'question': {
                    '_id': q['doc_id'],
                    'typecode': q['qtype'],
                    'status': False,
                    'right': 0.0,
                    'selected': True,
                    'userAnswer': [selected] if selected else [],
                },
                'note': '该题考点为%s，需要重点复习并重做。' % (q['kp_name'] or '核心概念'),
                'category': q['kp_name'],
                'resolved': False,
                'retryCount': random.randint(0, 3),
                'reviewStatus': 'pending',
                'addTime': (timezone.now() - timedelta(
                    days=random.randint(0, 20))).strftime('%Y/%m/%d %H:%M'),
            }},
        )

    def _link_articles_to_kb(self):
        linked = []
        docs = Document.objects.filter(collection='articles').order_by('pk')
        for doc in docs:
            if (doc.data or {}).get('status') != 'published':
                continue
            result = KnowledgeRAGService.add_article_to_index(doc, operator='seed_demo_data')
            if result and not result.get('error'):
                linked.append(result['article_code'])
            if len(linked) >= 2:
                break
        self.stdout.write('  [articles->knowledgebase] 已索引 %d 篇：%s'
                          % (len(linked), ', '.join(linked)))
        return linked

    # ---- 汇总 ----

    def _print_summary(self, history_created, notes_created, code_result, linked):
        stats = KnowledgeRAGService.get_stats()
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('== 汇总 =='))
        rows = [
            ('articles', Document.objects.filter(collection='articles').count()),
            ('  · 本次补编码', code_result['assigned']),
            ('knowledgebase', Document.objects.filter(collection='knowledgebase').count()),
            ('  · 其中来自文章', stats.get('article_count', 0)),
            ('  · 已索引文章', len(linked)),
            ('historys', Document.objects.filter(collection='historys').count()),
            ('notes', Document.objects.filter(collection='notes').count()),
            ('questions', Document.objects.filter(collection='questions').count()),
        ]
        for name, value in rows:
            self.stdout.write('  %-22s %s' % (name, value))
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('演示数据已就绪，可直接验证：'))
        self.stdout.write('  · 管理端 试卷分析（单考试需 >= 10 份答题记录）')
        self.stdout.write('  · 小程序 学习画像 / 学习报告（单用户需 >= 20 条记录）')
        self.stdout.write('  · 小程序 复习推荐 / 知识库问答（含文章溯源）')
        self.stdout.write('  · 管理端 知识库索引构建 / 文章编码与加入知识库')
