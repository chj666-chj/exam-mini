"""核心 API —— 复刻微信云开发数据库语义的 HTTP 接口。

接口一览（均返回 JSON，均为 csrf_exempt，仅限本地开发）：
- POST /api/login/                       -> {"openid": "..."}       模拟云函数 login
- POST /api/register/                    -> {"openid","nickname"}   账号注册（用户名+密码）
- POST /api/account-login/               -> {"openid","nickname"}   账号登录（用户名+密码）
- GET  /api/collections/<name>/          -> {"data": [...]}         集合查询（支持 ?字段=值 过滤、?count=1 计数）
- GET  /api/collections/<name>/<id>/     -> {"data": {...}}         按 _id 取文档
- POST /api/collections/<name>/          -> {"_id": "..."}           新增文档（data 带 _id 时为 upsert）
- PUT  /api/collections/<name>/<id>/     -> {"_id": "..."}           更新文档（整体替换）
- DELETE /api/collections/<name>/<id>/   -> {"deleted": true}
- GET  /api/question-stats/?id=<题目id>   -> 单题全站作答统计（跨用户聚合）
"""
import json
import random
import re
import time
import uuid

from django.db import IntegrityError, OperationalError
from django.db.models import Count, Q
from django.contrib.auth.hashers import make_password, check_password
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone

from .models import Document


def _db_write_with_retry(write_func, max_retries=6, base_delay=0.05):
    """SQLite 并发写入重试：database is locked / readonly 时抖动指数退避后重试。

    交卷时多个 addNote/addHistory 同时 POST，即使开启 WAL + busy_timeout
    仍可能偶发锁冲突（尤其高并发或磁盘 I/O 繁忙时），此处兜底重试。

    DEF-002 修复增强：
    · 重试次数 3 → 6（留足退避窗口）
    · 退避 0.1s 固定步进 → 0.05×2^n + 随机抖动（避免多个重试线程
      同步唤醒后再次撞锁的「惊群」效应）
    · 重试条件扩展：locked → locked + readonly（Windows WAL 并发已知问题）
    """
    for attempt in range(max_retries):
        try:
            return write_func()
        except OperationalError as exc:
            err_msg = str(exc).lower()
            retryable = 'locked' in err_msg or 'readonly' in err_msg
            if retryable and attempt < max_retries - 1:
                # Windows WAL 并发已知问题：连接的共享内存状态可能卡在 readonly，
                # 仅等待不够 —— 关闭当前连接强制下次查询重连，清除脏状态。
                from django.db import connection as _conn
                _conn.close()
                delay = base_delay * (2 ** attempt) + random.uniform(0, base_delay)
                time.sleep(delay)
                continue
            raise


def _upsert_document(collection, doc_id, data):
    """单语句写入，避免 update_or_create 的读后写锁升级（DEF-002 根因）。

    Document.objects.update_or_create() 内部走 get_or_create()：Django 将
    SELECT(get) 与 INSERT(create) 包在同一 transaction.atomic() 中，构成
    「读后写锁升级」。SQLite 对事务内的锁升级立即返回 SQLITE_BUSY，不触发
    busy_timeout 忙等待（PRAGMA 无效），导致并发交卷偶发 500。

    本实现拆为独立语句（autocommit 下各自独立提交，SQLite 正常遵守
    busy_timeout）：
    1. 先 SELECT（filter().first()）—— 纯读，无锁升级
    2. 命中 → obj.save(update_fields=['data']) —— 单语句 UPDATE
    3. 未命中 → create() —— 单语句 INSERT，捕获 IntegrityError 退化为 save

    Returns:
        (Document, created_flag) —— 与 update_or_create 返回值结构一致
    """
    existing = Document.objects.filter(collection=collection, doc_id=doc_id).first()
    if existing:
        existing.data = data
        existing.save(update_fields=['data'])
        return existing, False

    # 文档不存在 → CREATE（单语句 INSERT）
    try:
        obj = Document.objects.create(
            collection=collection, doc_id=doc_id, data=data
        )
        return obj, True
    except IntegrityError:
        # 并发下被抢先插入（unique_together 冲突）→ 退化为读取 + save
        existing = Document.objects.filter(collection=collection, doc_id=doc_id).first()
        if existing:
            existing.data = data
            existing.save(update_fields=['data'])
            return existing, False
        raise

# 允许通过 REST 访问的集合（白名单，防任意写入）
ALLOWED_COLLECTIONS = {
    'exam', 'subjects', 'questions', 'historys', 'notes',
    'history', 'test', 'record', 'profiles', 'articles',
    'testcases', 'favorites', 'feedback',
    'knowledgepoints', 'assessments', 'knowledgebase',
    'studynotes', 'ai_config', 'app_config', 'ai_jobs',
    'ai_learning_profile', 'ai_review_plans',
    'ai_kb_answers', 'ai_reports', 'ai_kb_index',
    'ai_exam_summaries', 'kp_question_index',
    'ai_usage_logs',
}

# 需要写权限校验的集合：这些集合保存用户私有的业务数据，
# 写入（新增/更新/删除）必须携带有效 openid，模拟云开发
# 「仅创建者可写」的集合权限；读操作保持公开以免阻断小程序首屏。
PRIVATE_COLLECTIONS = {'historys', 'notes', 'history', 'test', 'record', 'profiles', 'favorites', 'feedback', 'assessments', 'ai_reports'}


def _write_denied(reason):
    """写权限不足（对齐管理端错误码 40301）。"""
    return JsonResponse(
        {'code': 40301, 'message': reason, 'error': reason}, status=403
    )


def _check_write_permission(request, name):
    """校验写操作权限。

    规则：
    1. 开关关闭（EXAM_REQUIRE_OPENID_FOR_WRITE=False）时放行，便于裸数据调试；
    2. 私有集合写入必须携带非空 X-Openid（即小程序已完成 login）；
    3. 被管理端「停用」的用户（profiles.status=disabled）写入一律拒绝；
    4. 删除/更新时，若文档带 _openid 则必须与请求者一致（仅创建者可改删）。
    """
    if not getattr(settings, 'EXAM_REQUIRE_OPENID_FOR_WRITE', True):
        return None
    if name not in PRIVATE_COLLECTIONS:
        return None
    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return _write_denied('未登录：写入该集合需要先调用 login 获取 openid')
    # 管理端停用用户后，小程序端写入即时生效（读操作不拦截，保证历史数据可见）
    profile = Document.objects.filter(collection='profiles', data___openid=openid).first()
    if profile and profile.data.get('status') == 'disabled':
        return _write_denied('账号已停用，无法提交数据，请联系管理员')
    return None


def _check_owner(request, obj):
    """删除/更新时校验归属。"""
    if not getattr(settings, 'EXAM_REQUIRE_OPENID_FOR_WRITE', True):
        return None
    owner = obj.data.get('_openid')
    if not owner:
        return None
    openid = request.headers.get('X-Openid') or ''
    if owner != openid:
        return _write_denied('无权限：只能修改本人创建的数据')
    return None


def _json_body(request):
    if not request.body:
        return None, JsonResponse({'code': 40001, 'message': '请求体不能为空', 'error': '请求体不能为空'}, status=400)
    try:
        return json.loads(request.body), None
    except (ValueError, UnicodeDecodeError):
        return None, JsonResponse({'code': 40001, 'message': 'JSON 解析失败', 'error': 'JSON 解析失败'}, status=400)


def _parse_value(raw):
    """把 query string 中的值尽量还原为 JSON 类型。

    注意：小程序传来的查询值几乎都是字符串（页面 options），而文档字段
    可能是字符串也可能是数字（如 pid="001" vs code=1），因此过滤时
    对「原字符串」和「还原后的 JSON 值」做 OR 匹配。
    """
    if raw == 'true':
        return True
    if raw == 'false':
        return False
    try:
        return int(raw)
    except (TypeError, ValueError):
        pass
    try:
        return float(raw)
    except (TypeError, ValueError):
        return raw


# 查询字段名安全校验：只允许字母/数字/下划线，防止 ORM lookup 注入
_QUERY_FIELD_RE = re.compile(r'^[a-zA-Z0-9_]+$')


def _is_safe_field(name):
    """校验查询字段名，阻止 __ 语法注入意外 ORM lookup。"""
    return bool(_QUERY_FIELD_RE.match(name))


def _to_number(val):
    """把可能为字符串/None 的值安全转为 int/float。"""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return val
    try:
        return int(val)
    except (TypeError, ValueError):
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0


@csrf_exempt
def login(request):
    """模拟云函数 login：返回一个 openid。

    本地开发无微信鉴权，优先返回 historys 集合中答题记录最多的 openid，
    这样小程序「答题记录/错题本」页面一打开即可看到演示数据。
    """
    openid = settings.DEV_DEFAULT_OPENID
    top = (
        Document.objects.filter(collection='historys')
        .values('data___openid')
        .annotate(n=Count('id'))
        .order_by('-n')
        .first()
    )
    if top and top.get('data___openid'):
        openid = top['data___openid']
    return JsonResponse({'openid': openid})


# ---------------------------------------------------------------- 账号注册 / 账号登录
# 小程序端用户体系基于 openid（模拟微信云开发），profiles 集合存储用户档案。
# 账号注册/登录在 profiles 中增加 account + password 字段（Django PBKDF2 哈希），
# 注册时生成唯一 _openid（USER_<时间戳>_<随机>），登录时校验密码后返回该 openid。


def _validate_account(username):
    """校验用户名：3-20 位，仅允许字母/数字/下划线。返回 (ok, message)。"""
    if not username:
        return False, '用户名不能为空'
    if len(username) < 3 or len(username) > 20:
        return False, '用户名长度需 3-20 位'
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, '用户名仅支持字母、数字和下划线'
    return True, ''


def _validate_password(password):
    """校验密码：6-32 位。返回 (ok, message)。"""
    if not password:
        return False, '密码不能为空'
    if len(password) < 6 or len(password) > 32:
        return False, '密码长度需 6-32 位'
    return True, ''


@csrf_exempt
def register(request):
    """POST /api/register/  账号注册。

    请求体：{ "username": str, "password": str, "nickname": str? }
    流程：
      1. 校验 username（3-20 位字母/数字/下划线）、password（6-32 位）、nickname（可选，默认取 username）
      2. 检查 username 在 profiles 集合中是否已存在（account 字段）
      3. 生成唯一 _openid = USER_<时间戳>_<6位随机>
      4. 创建 profiles 文档：account / password(PBKDF2 哈希) / userInfo / status / createdAt
      5. 返回 { openid, nickname }

    返回信封：{ code: 0, message: "注册成功", data: { openid, nickname } }
    """
    if request.method != 'POST':
        return JsonResponse({'code': 40001, 'message': '方法不支持'}, status=405)

    try:
        body = json.loads(request.body) if request.body else {}
    except (ValueError, TypeError):
        return JsonResponse({'code': 40001, 'message': '请求体格式错误'}, status=400)

    username = str(body.get('username', '')).strip()
    password = str(body.get('password', ''))
    nickname = str(body.get('nickname', '')).strip() or username

    # 字段校验
    ok, msg = _validate_account(username)
    if not ok:
        return JsonResponse({'code': 40001, 'message': msg}, status=400)
    ok, msg = _validate_password(password)
    if not ok:
        return JsonResponse({'code': 40001, 'message': msg}, status=400)
    if len(nickname) > 20:
        return JsonResponse({'code': 40001, 'message': '昵称长度不能超过 20 位'}, status=400)

    # 检查用户名是否已被注册
    existing = Document.objects.filter(
        collection='profiles', data__account=username
    ).first()
    if existing:
        return JsonResponse({'code': 40901, 'message': '该用户名已被注册，请更换'}, status=409)

    # 生成唯一 openid
    openid = 'USER_' + str(int(time.time())) + '_' + uuid.uuid4().hex[:6]
    now_str = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M:%S')

    profile_data = {
        '_openid': openid,
        'account': username,
        'password': make_password(password),
        'userInfo': {
            'nickName': nickname,
            'avatarUrl': '',
        },
        'status': 'active',
        'vip': False,
        'isVip': False,
        'roles': ['user'],
        'createdAt': now_str,
    }

    doc_id = 'PROFILE_' + openid

    def _do_register():
        return _upsert_document('profiles', doc_id, profile_data)

    try:
        _db_write_with_retry(_do_register)
    except (IntegrityError, OperationalError) as exc:
        return JsonResponse(
            {'code': 50001, 'message': f'注册失败，请稍后重试：{str(exc)}'}, status=500
        )

    # 清除用户统计缓存（与管理端使用同一缓存失效函数，确保 key 一致）
    try:
        from adminapi.views_data import _invalidate_user_stats_cache
        _invalidate_user_stats_cache()
    except ImportError:
        from django.core.cache import cache
        cache.delete('admin:user_stats:all')

    return JsonResponse({
        'code': 0,
        'message': '注册成功',
        'data': {
            'openid': openid,
            'nickname': nickname,
        }
    })


@csrf_exempt
def account_login(request):
    """POST /api/account-login/  账号登录（用户名 + 密码）。

    请求体：{ "username": str, "password": str }
    流程：
      1. 校验字段非空
      2. 在 profiles 集合中按 account 查找用户
      3. 校验密码（PBKDF2 check_password）
      4. 校验账号状态（disabled → 拒绝）
      5. 返回 { openid, nickname, avatarUrl }

    返回信封：{ code: 0, message: "登录成功", data: { openid, nickname, avatarUrl } }
    """
    if request.method != 'POST':
        return JsonResponse({'code': 40001, 'message': '方法不支持'}, status=405)

    try:
        body = json.loads(request.body) if request.body else {}
    except (ValueError, TypeError):
        return JsonResponse({'code': 40001, 'message': '请求体格式错误'}, status=400)

    username = str(body.get('username', '')).strip()
    password = str(body.get('password', ''))

    if not username or not password:
        return JsonResponse({'code': 40001, 'message': '用户名和密码不能为空'}, status=400)

    profile_doc = Document.objects.filter(
        collection='profiles', data__account=username
    ).first()

    if not profile_doc:
        return JsonResponse({'code': 40101, 'message': '用户名或密码错误'}, status=401)

    profile_data = profile_doc.data or {}
    stored_hash = profile_data.get('password', '')

    if not stored_hash or not check_password(password, stored_hash):
        return JsonResponse({'code': 40101, 'message': '用户名或密码错误'}, status=401)

    # 校验账号状态
    if profile_data.get('status') == 'disabled':
        return JsonResponse({'code': 40301, 'message': '该账号已被停用，请联系管理员'}, status=403)

    openid = profile_data.get('_openid', '')
    if not openid:
        return JsonResponse({'code': 50001, 'message': '账号数据异常，缺少 openid'}, status=500)

    user_info = profile_data.get('userInfo', {}) or {}
    nickname = user_info.get('nickName', username)
    avatar_url = user_info.get('avatarUrl', '')

    # 检查是否需要强制改密码（管理员重置后标记）
    force_reset = bool(profile_data.get('forceResetPassword', False))

    return JsonResponse({
        'code': 0,
        'message': '登录成功',
        'data': {
            'openid': openid,
            'nickname': nickname,
            'avatarUrl': avatar_url,
            'forceResetPassword': force_reset,
        }
    })


# ---------------------------------------------------------------- 用户资料 & 密码管理
# 小程序端接口：
#   POST /api/profile/update/          更新个人资料（昵称/头像/邮箱/手机号/地址）
#   GET  /api/profile/                 获取个人资料
#   POST /api/change-password/         修改密码（原密码 + 新密码）
#   POST /api/forgot-password/         忘记密码（发送验证码到邮箱/手机号）
#   POST /api/reset-password/          重置密码（验证码 + 新密码）

# 验证码缓存 key 前缀（使用 Django cache 后端）
_RESET_CODE_KEY = 'pwd_reset_code:{account}'
_RESET_CODE_TTL = 300  # 5 分钟有效

# 邮箱 / 手机号正则
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
_PHONE_RE = re.compile(r'^1[3-9]\d{9}$')

# 密码强度：至少 6 位，包含字母和数字（与注册校验保持一致但增强）
_PWD_RE = re.compile(r'^(?=.*[a-zA-Z])(?=.*\d).{6,32}$')


def _check_password_strength(password):
    """检查密码强度：6-32 位，必须包含字母和数字。返回 (ok, message)。"""
    if not password:
        return False, '密码不能为空'
    if len(password) < 6 or len(password) > 32:
        return False, '密码长度需 6-32 位'
    if not _PWD_RE.match(password):
        return False, '密码需包含字母和数字'
    return True, ''


@csrf_exempt
def profile_update(request):
    """POST /api/profile/update/  更新个人资料。

    请求头：X-Openid: <openid>
    请求体：{ nickname?, avatarUrl?, email?, phone?, address? }（只更新传入的字段）

    返回信封：{ code: 0, message: "保存成功", data: { ...更新后的资料 } }
    """
    if request.method != 'POST':
        return JsonResponse({'code': 40001, 'message': '方法不支持'}, status=405)

    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return JsonResponse({'code': 40101, 'message': '未登录，请先登录'}, status=401)

    try:
        body = json.loads(request.body) if request.body else {}
    except (ValueError, TypeError):
        return JsonResponse({'code': 40001, 'message': '请求体格式错误'}, status=400)

    # 查找用户 profile
    profile_doc = Document.objects.filter(
        collection='profiles', data___openid=openid
    ).first()
    if not profile_doc:
        return JsonResponse({'code': 40401, 'message': '用户资料不存在'}, status=404)

    data = dict(profile_doc.data) if profile_doc.data else {}
    user_info = data.get('userInfo') or {}
    if not isinstance(user_info, dict):
        user_info = {}

    changed = False

    # 昵称
    if 'nickname' in body:
        nick = str(body.get('nickname', '')).strip()
        if nick and len(nick) <= 20:
            user_info['nickName'] = nick
            changed = True
        elif nick and len(nick) > 20:
            return JsonResponse({'code': 40001, 'message': '昵称长度不能超过 20 位'}, status=400)

    # 头像
    if 'avatarUrl' in body:
        avatar = str(body.get('avatarUrl', '')).strip()
        user_info['avatarUrl'] = avatar
        changed = True

    # 邮箱
    if 'email' in body:
        email = str(body.get('email', '')).strip()
        if email and not _EMAIL_RE.match(email):
            return JsonResponse({'code': 40001, 'message': '邮箱格式不正确'}, status=400)
        data['email'] = email
        changed = True

    # 手机号
    if 'phone' in body:
        phone = str(body.get('phone', '')).strip()
        if phone and not _PHONE_RE.match(phone):
            return JsonResponse({'code': 40001, 'message': '手机号格式不正确（需 11 位数字）'}, status=400)
        data['phone'] = phone
        changed = True

    # 地址
    if 'address' in body:
        address = str(body.get('address', '')).strip()
        if len(address) > 200:
            return JsonResponse({'code': 40001, 'message': '地址长度不能超过 200 位'}, status=400)
        data['address'] = address
        changed = True

    if not changed:
        return JsonResponse({'code': 0, 'message': '无需要更新的字段', 'data': {}})

    data['userInfo'] = user_info

    def _do_save():
        profile_doc.data = data
        profile_doc.save(update_fields=['data'])

    try:
        _db_write_with_retry(_do_save)
    except (IntegrityError, OperationalError) as exc:
        return JsonResponse({'code': 50001, 'message': f'保存失败：{str(exc)}'}, status=500)

    # 清除管理端用户统计缓存
    try:
        from adminapi.views_data import _invalidate_user_stats_cache
        _invalidate_user_stats_cache()
    except ImportError:
        pass

    return JsonResponse({
        'code': 0,
        'message': '保存成功',
        'data': {
            'nickname': user_info.get('nickName', ''),
            'avatarUrl': user_info.get('avatarUrl', ''),
            'email': data.get('email', ''),
            'phone': data.get('phone', ''),
            'address': data.get('address', ''),
        }
    })


@csrf_exempt
def profile_get(request):
    """GET /api/profile/  获取个人资料。

    请求头：X-Openid: <openid>
    返回信封：{ code: 0, data: { nickname, avatarUrl, email, phone, address, account, createdAt } }
    """
    if request.method != 'GET':
        return JsonResponse({'code': 40001, 'message': '方法不支持'}, status=405)

    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return JsonResponse({'code': 40101, 'message': '未登录，请先登录'}, status=401)

    profile_doc = Document.objects.filter(
        collection='profiles', data___openid=openid
    ).first()
    if not profile_doc:
        return JsonResponse({'code': 40401, 'message': '用户资料不存在'}, status=404)

    data = profile_doc.data or {}
    user_info = data.get('userInfo') or {}

    return JsonResponse({
        'code': 0,
        'data': {
            'account': data.get('account', ''),
            'nickname': user_info.get('nickName', ''),
            'avatarUrl': user_info.get('avatarUrl', ''),
            'email': data.get('email', ''),
            'phone': data.get('phone', ''),
            'address': data.get('address', ''),
            'createdAt': data.get('createdAt', ''),
        }
    })


@csrf_exempt
def change_password(request):
    """POST /api/change-password/  修改密码（需登录，验证原密码）。

    请求头：X-Openid: <openid>
    请求体：{ oldPassword, newPassword }

    返回信封：{ code: 0, message: "密码修改成功" }
    """
    if request.method != 'POST':
        return JsonResponse({'code': 40001, 'message': '方法不支持'}, status=405)

    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return JsonResponse({'code': 40101, 'message': '未登录，请先登录'}, status=401)

    try:
        body = json.loads(request.body) if request.body else {}
    except (ValueError, TypeError):
        return JsonResponse({'code': 40001, 'message': '请求体格式错误'}, status=400)

    old_pwd = str(body.get('oldPassword', ''))
    new_pwd = str(body.get('newPassword', ''))

    if not old_pwd:
        return JsonResponse({'code': 40001, 'message': '请输入原密码'}, status=400)

    # 新密码强度校验
    ok, msg = _check_password_strength(new_pwd)
    if not ok:
        return JsonResponse({'code': 40001, 'message': msg}, status=400)

    profile_doc = Document.objects.filter(
        collection='profiles', data___openid=openid
    ).first()
    if not profile_doc:
        return JsonResponse({'code': 40401, 'message': '用户资料不存在'}, status=404)

    data = dict(profile_doc.data) if profile_doc.data else {}
    stored_hash = data.get('password', '')

    # 游客模式注册的用户没有 password 字段 → 不允许通过此接口改密
    if not stored_hash:
        return JsonResponse({'code': 40301, 'message': '当前账号未设置密码（游客模式），无法修改密码'}, status=403)

    if not check_password(old_pwd, stored_hash):
        return JsonResponse({'code': 40101, 'message': '原密码不正确'}, status=401)

    # 新密码不能与原密码相同
    if check_password(new_pwd, stored_hash):
        return JsonResponse({'code': 40001, 'message': '新密码不能与原密码相同'}, status=400)

    # 更新密码
    data['password'] = make_password(new_pwd)
    # 清除"需强制改密码"标记
    data.pop('forceResetPassword', None)

    def _do_save():
        profile_doc.data = data
        profile_doc.save(update_fields=['data'])

    try:
        _db_write_with_retry(_do_save)
    except (IntegrityError, OperationalError) as exc:
        return JsonResponse({'code': 50001, 'message': f'密码修改失败：{str(exc)}'}, status=500)

    return JsonResponse({'code': 0, 'message': '密码修改成功'})


@csrf_exempt
def forgot_password(request):
    """POST /api/forgot-password/  忘记密码（发送验证码）。

    请求体：{ account, channel: 'email'|'phone' }
    流程：
      1. 按 account（用户名）查找用户
      2. 检查用户是否绑定了对应渠道（邮箱/手机号）
      3. 生成 6 位数字验证码，存入 cache（5 分钟有效）
      4. 发送验证码（开发环境直接返回验证码，生产环境发邮件/短信）

    返回信封：{ code: 0, message: "验证码已发送", data: { devCode?: "123456" } }
    """
    from django.core.cache import cache

    if request.method != 'POST':
        return JsonResponse({'code': 40001, 'message': '方法不支持'}, status=405)

    try:
        body = json.loads(request.body) if request.body else {}
    except (ValueError, TypeError):
        return JsonResponse({'code': 40001, 'message': '请求体格式错误'}, status=400)

    account = str(body.get('account', '')).strip()
    channel = str(body.get('channel', 'email')).strip()

    if not account:
        return JsonResponse({'code': 40001, 'message': '请输入用户名'}, status=400)
    if channel not in ('email', 'phone'):
        return JsonResponse({'code': 40001, 'message': '渠道仅支持 email 或 phone'}, status=400)

    # 查找用户
    profile_doc = Document.objects.filter(
        collection='profiles', data__account=account
    ).first()
    if not profile_doc:
        # 安全考虑：不暴露用户名是否存在
        return JsonResponse({'code': 0, 'message': '若该用户名存在，验证码已发送至绑定渠道'})

    data = profile_doc.data or {}
    target = ''
    if channel == 'email':
        target = data.get('email', '')
        if not target:
            return JsonResponse({'code': 40001, 'message': '该账号未绑定邮箱，无法通过邮箱找回密码'}, status=400)
    else:
        target = data.get('phone', '')
        if not target:
            return JsonResponse({'code': 40001, 'message': '该账号未绑定手机号，无法通过手机号找回密码'}, status=400)

    # 生成 6 位验证码
    code = str(random.randint(100000, 999999))
    cache.set(_RESET_CODE_KEY.format(account=account), code, _RESET_CODE_TTL)

    # 开发环境：直接返回验证码（生产环境应发邮件/短信）
    # TODO: 生产环境接入邮件/短信服务
    resp_data = {}
    if getattr(settings, 'DEBUG', False):
        resp_data['devCode'] = code
        # 遮罩目标地址
        if channel == 'email':
            resp_data['target'] = target[:2] + '***' + target[target.index('@'):]
        else:
            resp_data['target'] = target[:3] + '****' + target[-4:]

    return JsonResponse({
        'code': 0,
        'message': '验证码已发送' + ('（开发环境直接返回）' if getattr(settings, 'DEBUG', False) else ''),
        'data': resp_data
    })


@csrf_exempt
def reset_password(request):
    """POST /api/reset-password/  重置密码（验证码 + 新密码）。

    请求体：{ account, code, newPassword }
    流程：
      1. 校验验证码
      2. 校验新密码强度
      3. 更新密码，清除验证码缓存

    返回信封：{ code: 0, message: "密码重置成功" }
    """
    from django.core.cache import cache

    if request.method != 'POST':
        return JsonResponse({'code': 40001, 'message': '方法不支持'}, status=405)

    try:
        body = json.loads(request.body) if request.body else {}
    except (ValueError, TypeError):
        return JsonResponse({'code': 40001, 'message': '请求体格式错误'}, status=400)

    account = str(body.get('account', '')).strip()
    code = str(body.get('code', '')).strip()
    new_pwd = str(body.get('newPassword', ''))

    if not account or not code:
        return JsonResponse({'code': 40001, 'message': '用户名和验证码不能为空'}, status=400)

    # 新密码强度校验
    ok, msg = _check_password_strength(new_pwd)
    if not ok:
        return JsonResponse({'code': 40001, 'message': msg}, status=400)

    # 校验验证码
    cached_code = cache.get(_RESET_CODE_KEY.format(account=account))
    if not cached_code:
        return JsonResponse({'code': 40001, 'message': '验证码已过期或未发送，请重新获取'}, status=400)
    if cached_code != code:
        return JsonResponse({'code': 40101, 'message': '验证码不正确'}, status=401)

    # 查找用户并更新密码
    profile_doc = Document.objects.filter(
        collection='profiles', data__account=account
    ).first()
    if not profile_doc:
        return JsonResponse({'code': 40401, 'message': '用户不存在'}, status=404)

    data = dict(profile_doc.data) if profile_doc.data else {}
    data['password'] = make_password(new_pwd)
    # 清除"需强制改密码"标记
    data.pop('forceResetPassword', None)

    def _do_save():
        profile_doc.data = data
        profile_doc.save(update_fields=['data'])

    try:
        _db_write_with_retry(_do_save)
    except (IntegrityError, OperationalError) as exc:
        return JsonResponse({'code': 50001, 'message': f'密码重置失败：{str(exc)}'}, status=500)

    # 清除验证码
    cache.delete(_RESET_CODE_KEY.format(account=account))

    return JsonResponse({'code': 0, 'message': '密码重置成功，请使用新密码登录'})


@csrf_exempt
def collection_list(request, name):
    """GET 查询集合 / POST 新增文档。"""
    if name not in ALLOWED_COLLECTIONS:
        return JsonResponse({'code': 40401, 'message': f'集合 {name} 不在白名单中', 'error': f'集合 {name} 不在白名单中'}, status=404)

    if request.method == 'GET':
        qs = Document.objects.filter(collection=name)
        # P0-2 修复：私有集合数据隔离，仅返回当前用户的数据
        if name in PRIVATE_COLLECTIONS:
            openid = request.headers.get('X-Openid') or ''
            if not openid:
                return JsonResponse({'data': []})
            qs = qs.filter(data___openid=openid)
        # articles 集合特殊处理：未指定 status 时只返回已发布文章
        if name == 'articles' and 'status' not in request.GET:
            qs = qs.filter(data__status='published')
        count_only = request.GET.get('count') == '1'
        # where 过滤：除 count 外的每个查询参数都视为对文档字段的等值匹配
        for key, raw in request.GET.items():
            if key == 'count':
                continue
            if key == '_openid':
                lookup = 'data___openid'
                qs = qs.filter(Q(**{lookup: raw}) | Q(**{lookup: _parse_value(raw)}))
            elif '__contains' in key:
                # 数组包含查询：field__contains=value
                # SQLite 不支持 JSONField __contains，改用 json_each 原生函数
                field = key.split('__contains')[0]
                if not _is_safe_field(field):
                    continue  # P0-6 修复：跳过非法字段名
                where_clause = (
                    "EXISTS (SELECT 1 FROM json_each("
                    "json_extract(data, '$." + field + "')) "
                    "WHERE json_each.value = %s)"
                )
                qs = qs.extra(where=[where_clause], params=[raw])
            else:
                if not _is_safe_field(key):
                    continue  # P0-6 修复：跳过非法字段名
                lookup = f'data__{key}'
                # 字符串原值 与 还原后的 JSON 值 OR 匹配，兼容两种存储类型
                qs = qs.filter(Q(**{lookup: raw}) | Q(**{lookup: _parse_value(raw)}))
        if count_only:
            return JsonResponse({'total': qs.count()})
        docs = [d.to_client() for d in qs.order_by('pk')]
        return JsonResponse({'data': docs})

    if request.method == 'POST':
        denied = _check_write_permission(request, name)
        if denied:
            return denied
        data, err = _json_body(request)
        if err:
            return err
        if not isinstance(data, dict):
            return JsonResponse({'code': 40001, 'message': '文档必须是 JSON 对象', 'error': '文档必须是 JSON 对象'}, status=400)
        # articles 集合特殊处理：自动注入默认字段
        if name == 'articles':
            now_str = timezone.localtime(timezone.now()).strftime('%Y/%m/%d %H:%M')
            data.setdefault('status', 'pending')
            data.setdefault('views', 0)
            data.setdefault('createTime', now_str)
            data.setdefault('updateTime', now_str)
            data.setdefault('images', [])
            data.setdefault('tags', [])
            if not data.get('author'):
                data['author'] = '匿名用户'
        # 云数据库语义：add 时自动注入 _openid（请求头 X-Openid）
        if '_openid' not in data:
            header_openid = request.headers.get('X-Openid')
            if header_openid:
                data['_openid'] = header_openid
        doc_id = data.pop('_id', None)
        if doc_id is not None:
            doc_id = str(doc_id)
        else:
            # P0 修复：客户端未指定 _id 时自动生成唯一 doc_id
            # 原实现 doc_id=None → update_or_create(collection=name, doc_id=None)：
            #   · 第一条 create 后，后续 add 的 get() 会命中它并覆写 → 所有 note 挤成 1 条
            #   · 并发请求竞态可产生多条 doc_id=None → get() 抛 MultipleObjectsReturned → 500
            # 云开发 add() 会自动生成唯一 _id，此处对齐该语义
            import uuid
            doc_id = uuid.uuid4().hex
        # P0-1 修复：IDOR 防护 — 私有集合 upsert 时校验已有文档归属
        if doc_id is not None and name in PRIVATE_COLLECTIONS:
            existing = Document.objects.filter(collection=name, doc_id=doc_id).first()
            if existing:
                owner_err = _check_owner(request, existing)
                if owner_err:
                    return owner_err
        obj, _created = _db_write_with_retry(
            lambda: _upsert_document(name, doc_id, data)
        )
        # 文章：自动生成唯一编码 ART-YYYYMMDD-NNNN（小程序投稿同样适用）
        if name == 'articles':
            from adminapi import article_code
            article_code.assign_article_code(obj)
        # 写入私有集合时清除用户统计缓存
        if name in PRIVATE_COLLECTIONS:
            from django.core.cache import cache
            cache.delete('admin:user_stats:all')
        return JsonResponse({'_id': obj.doc_id if obj.doc_id else str(obj.pk)})

    return JsonResponse({'code': 40001, 'message': '方法不支持', 'error': '方法不支持'}, status=405)


@csrf_exempt
def collection_detail(request, name, doc_id):
    """按 _id 操作单个文档。"""
    if name not in ALLOWED_COLLECTIONS:
        return JsonResponse({'code': 40401, 'message': f'集合 {name} 不在白名单中', 'error': f'集合 {name} 不在白名单中'}, status=404)

    obj = None
    try:
        obj = Document.objects.get(collection=name, doc_id=doc_id)
    except Document.DoesNotExist:
        # 云数据库 add 未指定 _id 时返回自动 id，支持按该 id 读取/删除
        if doc_id.isdigit():
            try:
                obj = Document.objects.get(collection=name, pk=int(doc_id), doc_id=None)
            except Document.DoesNotExist:
                pass
    if obj is None:
        return JsonResponse({'code': 40401, 'message': '文档不存在', 'error': '文档不存在', 'errCode': -1}, status=404)

    if request.method == 'GET':
        # articles 集合特殊处理：自动增加浏览量
        if name == 'articles':
            obj.data['views'] = obj.data.get('views', 0) + 1
            obj.save()
        return JsonResponse({'data': obj.to_client()})

    if request.method in ('PUT', 'PATCH'):
        denied = _check_write_permission(request, name) or _check_owner(request, obj)
        if denied:
            return denied
        data, err = _json_body(request)
        if err:
            return err
        if request.method == 'PUT':
            merged = dict(obj.data)
            merged.update(data)
            # 归属字段不可被客户端改写
            if '_openid' in obj.data:
                merged['_openid'] = obj.data['_openid']
            else:
                merged.pop('_openid', None)
            obj.data = merged
        else:
            obj.data.update(data)
        obj.save()
        return JsonResponse({'_id': obj.doc_id})

    if request.method == 'DELETE':
        denied = _check_write_permission(request, name) or _check_owner(request, obj)
        if denied:
            return denied
        obj.delete()
        return JsonResponse({'deleted': True})

    return JsonResponse({'code': 40001, 'message': '方法不支持', 'error': '方法不支持'}, status=405)


@csrf_exempt
def ranking(request):
    """GET /api/ranking/ — 排行榜（全用户聚合，不受私有集合隔离限制）。

    返回：
      {
        "board":   [ {rank, openid, nickname, avatar, solved, acc}, ... ],  // 前 100
        "myStats": { rank, latestScore, passCount, examCount, predictScore,
                      solvedCount, accuracy, accuracyRank, persistDays,
                      persistRank, unsolvedCount, totalPassDays, weekDays, weekPass },
        "myRank":  int,       // 当前用户在全部用户中的排名（可能 >100）
        "totalQuestions": int
      }
    """
    import datetime

    if request.method != 'GET':
        return JsonResponse({'code': 40001, 'message': '方法不支持', 'error': '方法不支持'}, status=405)

    openid = request.headers.get('X-Openid') or ''

    # ---- 1. 加载 profiles 昵称/头像 ----
    profile_map = {}
    for doc in Document.objects.filter(collection='profiles'):
        oid = doc.data.get('_openid', '')
        if not oid:
            continue
        info = doc.data.get('userInfo', {}) or {}
        profile_map[oid] = {
            'nickname': info.get('nickName', ''),
            'avatar': info.get('avatarUrl', ''),
        }

    # ---- 2. 加载全部 historys，按用户聚合 ----
    by_user = {}
    for doc in Document.objects.filter(collection='historys'):
        data = doc.data or {}
        oid = data.get('_openid', '')
        if not oid:
            continue
        nums = _to_number(data.get('nums', 0))
        right_num = _to_number(data.get('rightNum', 0))
        user_info = data.get('userInfo', {}) or {}
        create_time = data.get('createTime', '')

        if oid not in by_user:
            p = profile_map.get(oid, {})
            by_user[oid] = {
                'openid': oid,
                'nickname': user_info.get('nickName', '') or p.get('nickname', '') or ('用户' + oid[-4:]),
                'avatar': user_info.get('avatarUrl', '') or p.get('avatar', ''),
                'solved': 0, 'right': 0, 'pass_count': 0,
                'exam_count': 0, 'days': set(), 'records': [],
            }
        u = by_user[oid]
        u['solved'] += nums
        u['right'] += right_num
        u['exam_count'] += 1
        if nums and right_num / nums >= 0.6:
            u['pass_count'] += 1
        # 解析日期（兼容 "YYYY/MM/DD HH:MM" 和 "YYYY-MM-DD HH:MM"）
        date_str = (create_time or '').split(' ')[0]
        try:
            parsed_date = datetime.datetime.strptime(date_str, '%Y/%m/%d').date()
            u['days'].add(parsed_date)
        except (ValueError, TypeError):
            try:
                parsed_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                u['days'].add(parsed_date)
            except (ValueError, TypeError):
                pass
        u['records'].append({'nums': nums, 'rightNum': right_num})

    # ---- 2.5 补全无答题记录但有用户档案的用户 ----
    for oid, p in profile_map.items():
        if oid not in by_user:
            by_user[oid] = {
                'openid': oid,
                'nickname': p.get('nickname', '') or ('用户' + oid[-4:]),
                'avatar': p.get('avatar', ''),
                'solved': 0, 'right': 0, 'pass_count': 0,
                'exam_count': 0, 'days': set(), 'records': [],
            }

    # ---- 3. 构建完整排行榜 ----
    full_board = []
    for oid, u in by_user.items():
        acc = round(u['right'] / u['solved'] * 100) if u['solved'] else 0
        full_board.append({
            'openid': oid,
            'nickname': u['nickname'],
            'avatar': u['avatar'],
            'solved': u['solved'],
            'acc': acc,
            'days': len(u['days']),
        })
    full_board.sort(key=lambda x: (-x['acc'], -x['solved'], -x['days']))

    # 前 100 名
    top_100 = []
    for i, item in enumerate(full_board[:100]):
        top_100.append({**item, 'rank': i + 1})

    # ---- 4. 当前用户排名 ----
    my_rank = 0
    for i, item in enumerate(full_board):
        if item['openid'] == openid:
            my_rank = i + 1
            break

    # 正确率排名 & 坚持天数排名
    acc_sorted = sorted(full_board, key=lambda x: -x['acc'])
    acc_rank = next((i + 1 for i, x in enumerate(acc_sorted) if x['openid'] == openid), 0)
    days_sorted = sorted(full_board, key=lambda x: -x['days'])
    persist_rank = next((i + 1 for i, x in enumerate(days_sorted) if x['openid'] == openid), 0)

    # ---- 5. 题库总数 ----
    total_questions = Document.objects.filter(collection='questions').count()

    # ---- 6. 当前用户详细统计 ----
    my_stats = {
        'rank': my_rank,
        'latestScore': 0, 'passCount': 0, 'examCount': 0,
        'predictScore': 0, 'solvedCount': 0, 'accuracy': 0,
        'accuracyRank': acc_rank, 'persistDays': 0, 'persistRank': persist_rank,
        'unsolvedCount': total_questions, 'totalPassDays': 0,
        'weekDays': [], 'weekPass': 0,
    }

    if openid in by_user:
        u = by_user[openid]
        acc = round(u['right'] / u['solved'] * 100) if u['solved'] else 0
        latest = u['records'][-1] if u['records'] else None
        latest_score = round(latest['rightNum'] / latest['nums'] * 100) if (latest and latest['nums']) else 0

        # 本周达标（周一至周日）
        today = datetime.date.today()
        monday = today - datetime.timedelta(days=today.weekday())
        day_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        week_days = []
        week_pass = 0
        for i in range(7):
            d = monday + datetime.timedelta(days=i)
            passed = d in u['days']
            if passed:
                week_pass += 1
            week_days.append({
                'key': f'{d.year}/{d.month}/{d.day}{i}',
                'label': day_labels[i],
                'pass': passed,
            })

        my_stats.update({
            'latestScore': latest_score,
            'passCount': u['pass_count'],
            'examCount': u['exam_count'],
            'predictScore': acc,
            'solvedCount': u['solved'],
            'accuracy': acc,
            'persistDays': len(u['days']),
            'unsolvedCount': max(0, total_questions - u['solved']),
            'totalPassDays': len(u['days']),
            'weekDays': week_days,
            'weekPass': week_pass,
        })

    return JsonResponse({
        'board': top_100,
        'myStats': my_stats,
        'myRank': my_rank,
        'totalQuestions': total_questions,
    })


def _is_correct_value(v):
    """选项 value 是否为「正确项」——兼容 1(int) / '1'(str) / True(bool)。"""
    if v is True:
        return True
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return v == 1
    if isinstance(v, str):
        return v.strip() == '1'
    return False


def _correct_codes_of(question_data):
    """取题目标准答案编号列表（先 options.value，再回退 answer 字段）。"""
    options = question_data.get('options') or []
    if not isinstance(options, list):
        options = []
    codes = []
    for opt in options:
        if not isinstance(opt, dict):
            continue
        if _is_correct_value(opt.get('value')) or opt.get('isCorrect') is True:
            c = str(opt.get('code') or '').strip().upper()
            if c and c not in codes:
                codes.append(c)
    if codes:
        return sorted(codes)

    ans = str(question_data.get('answer') or '').strip().upper()
    if not ans:
        return []
    opt_codes = []
    for opt in options:
        if not isinstance(opt, dict):
            continue
        c = str(opt.get('code') or '').strip().upper()
        if c and c not in opt_codes:
            opt_codes.append(c)
    if not opt_codes:
        return []
    if ans in opt_codes:
        return [ans]
    return sorted({ch for ch in ans if ch in opt_codes})


def _normalize_codes(raw):
    """归一化作答编号：转字符串、去空、去重、排序。

    注意：None / 空串必须跳过 —— Python 的 str(None) 会得到 'None'，
    若不显式过滤会被当成一个合法选项编号（与小程序端 normalizeCode 的语义对齐）。
    """
    if not isinstance(raw, list):
        return []
    out = set()
    for c in raw:
        if c is None:
            continue
        s = str(c).strip().upper()
        if s:
            out.add(s)
    return sorted(out)


@csrf_exempt
def question_stats(request):
    """GET /api/question-stats/?id=<题目id> —— 单题全站作答统计。

    与 /api/ranking/ 同属「需要跨用户聚合」的场景：
    historys 属于 PRIVATE_COLLECTIONS，走 collection_list 会按 X-Openid 过滤，
    只能拿到当前用户自己的记录，无法计算全站作答次数与正确率，故单独提供本接口。

    返回：
      {
        "data": {
          "totalAttempts": int,   # 全站作答该题的次数（有有效作答的记录数）
          "correctCount":  int,   # 其中答对的次数
          "correctRate":   int,   # 正确率（0-100 整数）
          "correctCodes":  [str]  # 该题标准答案编号，便于前端核对
        }
      }
    """
    if request.method != 'GET':
        return JsonResponse({'code': 40001, 'message': '方法不支持', 'error': '方法不支持'}, status=405)

    question_id = (request.GET.get('id') or request.GET.get('questionId') or '').strip()
    if not question_id:
        return JsonResponse({'code': 40001, 'message': '缺少题目 id', 'error': '缺少题目 id'}, status=400)

    qdoc = Document.objects.filter(collection='questions', doc_id=question_id).first()
    correct_codes = _correct_codes_of(qdoc.data) if qdoc else []

    total_attempts = 0
    correct_count = 0
    # 全量扫描：此处刻意不做 _openid 过滤，统计的是「全站」数据
    for doc in Document.objects.filter(collection='historys'):
        data = doc.data or {}
        items = data.get('items')
        score_arr = data.get('score_arr')
        if not isinstance(items, list) or not isinstance(score_arr, list):
            continue
        if question_id not in items:
            continue
        idx = items.index(question_id)
        if idx < 0 or idx >= len(score_arr):
            continue
        user_ans = _normalize_codes(score_arr[idx])
        if not user_ans:
            continue          # 未作答不计入
        total_attempts += 1
        if correct_codes and user_ans == correct_codes:
            correct_count += 1

    correct_rate = round(correct_count / total_attempts * 100) if total_attempts else 0

    return JsonResponse({
        'data': {
            'totalAttempts': total_attempts,
            'correctCount': correct_count,
            'correctRate': correct_rate,
            'correctCodes': correct_codes,
        }
    })


@csrf_exempt
def unknown_endpoint(request, path=''):
    """兜底：/api/ 下未匹配的请求。"""
    return JsonResponse(
        {'code': 40401, 'message': '接口不存在', 'error': '接口不存在'}, status=404
    )


@csrf_exempt
def upload_image(request):
    """POST /api/upload/  公共图片上传接口（小程序端文章图片）。"""
    import os
    import uuid

    if request.method != 'POST':
        return JsonResponse({'code': 40001, 'message': '方法不支持', 'error': '方法不支持'}, status=405)

    file_obj = request.FILES.get('file')
    if not file_obj:
        return JsonResponse({'code': 40001, 'message': '未收到文件', 'error': '未收到文件'}, status=400)

    ext = os.path.splitext(file_obj.name)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
        return JsonResponse({'code': 40001, 'message': '仅支持 jpg/png/gif/webp 格式', 'error': '仅支持图片格式'}, status=400)

    if file_obj.size > 5 * 1024 * 1024:
        return JsonResponse({'code': 40001, 'message': '图片大小不能超过 5MB', 'error': '图片过大'}, status=400)

    month = timezone.now().strftime('%Y%m')
    upload_dir = os.path.join(str(settings.MEDIA_ROOT), 'uploads', month)
    os.makedirs(upload_dir, exist_ok=True)

    filename = uuid.uuid4().hex[:16] + ext
    filepath = os.path.join(upload_dir, filename)

    with open(filepath, 'wb') as f:
        for chunk in file_obj.chunks():
            f.write(chunk)

    url = settings.MEDIA_URL + 'uploads/' + month + '/' + filename
    return JsonResponse({'url': url, 'name': file_obj.name, 'size': file_obj.size})


# ---------------------------------------------------------------- 激活码自助激活
@csrf_exempt
def activation_redeem(request):
    """POST /api/activation/redeem/  激活码自助激活（小程序端）。

    请求头：X-Openid: <openid>
    请求体：{ "code": "123456" }

    流程：
      1. 校验 openid 与 code（6 位数字）
      2. 在 activation_codes 集合中查找该码
      3. 校验状态（active）、过期时间
      4. 写入 profiles 文档：vip=True, roles 追加 'vip'
      5. 标记激活码为 used（usedBy, usedAt, status=used）
      6. 返回成功 + VIP 信息

    返回信封：{ code: 0, message: "激活成功", data: { vip: true, vipDuration: 30 } }
    """
    import json as _json

    if request.method != 'POST':
        return JsonResponse({'code': 40001, 'message': '方法不支持'}, status=405)

    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return JsonResponse({'code': 40101, 'message': '未登录：请先登录后再激活'}, status=401)

    try:
        body = _json.loads(request.body) if request.body else {}
    except (ValueError, TypeError):
        body = {}

    code = str(body.get('code', '')).strip()
    if not code or not (code.isdigit() and len(code) == 6):
        return JsonResponse({'code': 40001, 'message': '激活码格式错误：请输入 6 位数字'}, status=400)

    # 查找激活码
    code_doc = Document.objects.filter(
        collection='activation_codes', data__code=code
    ).first()

    if not code_doc:
        return JsonResponse({'code': 40401, 'message': '激活码不存在，请检查后重新输入'}, status=404)

    code_data = code_doc.data or {}
    status_val = str(code_data.get('status', '')).strip()

    if status_val == 'used':
        used_by = str(code_data.get('usedBy', ''))
        if used_by == openid:
            return JsonResponse({'code': 40901, 'message': '该激活码您已使用过，无需重复激活'}, status=409)
        return JsonResponse({'code': 40901, 'message': '该激活码已被其他用户使用'}, status=409)

    if status_val == 'disabled':
        return JsonResponse({'code': 40301, 'message': '该激活码已被停用'}, status=403)

    if status_val != 'active':
        return JsonResponse({'code': 40301, 'message': f'该激活码状态异常（{status_val}）'}, status=403)

    # 校验过期时间
    expire_at = str(code_data.get('expireAt', '')).strip()
    if expire_at:
        try:
            from datetime import datetime
            # 兼容 "YYYY-MM-DD" 和 "YYYY-MM-DD HH:MM:SS" 两种格式
            expire_dt = datetime.strptime(expire_at[:19], '%Y-%m-%d %H:%M:%S') if len(expire_at) > 10 \
                else datetime.strptime(expire_at, '%Y-%m-%d')
            expire_dt = timezone.make_aware(expire_dt, timezone.get_default_timezone()) if timezone.is_naive(expire_dt) else expire_dt
            if timezone.now() > expire_dt:
                return JsonResponse({'code': 40301, 'message': '该激活码已过期'}, status=403)
        except (ValueError, TypeError):
            pass  # 解析失败不阻断（容错）

    vip_duration = code_data.get('vipDuration', 30)

    # 写入 profiles：设置 vip=True，追加 roles
    def _do_activate():
        profile_doc = Document.objects.filter(
            collection='profiles', data___openid=openid
        ).first()

        now_str = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M:%S')

        if profile_doc:
            p_data = dict(profile_doc.data) if profile_doc.data else {}
            p_data['vip'] = True
            p_data['isVip'] = True
            # 追加 roles
            roles = p_data.get('roles') or []
            if not isinstance(roles, list):
                roles = []
            if 'vip' not in roles:
                roles.append('vip')
            p_data['roles'] = roles
            p_data['vipActivatedAt'] = now_str
            p_data['vipDuration'] = vip_duration
            # 计算到期时间
            if vip_duration and vip_duration > 0:
                from datetime import timedelta
                expire_date = timezone.now() + timedelta(days=int(vip_duration))
                p_data['vipExpireAt'] = expire_date.strftime('%Y-%m-%d %H:%M:%S')
            else:
                p_data['vipExpireAt'] = 'permanent'  # 永久

            profile_doc.data = p_data
            profile_doc.save()
        else:
            # 用户尚无 profile 文档，创建一个
            from datetime import timedelta
            p_data = {
                '_openid': openid,
                'userInfo': {},
                'vip': True,
                'isVip': True,
                'roles': ['vip'],
                'vipActivatedAt': now_str,
                'vipDuration': vip_duration,
            }
            if vip_duration and vip_duration > 0:
                expire_date = timezone.now() + timedelta(days=int(vip_duration))
                p_data['vipExpireAt'] = expire_date.strftime('%Y-%m-%d %H:%M:%S')
            else:
                p_data['vipExpireAt'] = 'permanent'

            Document.objects.create(collection='profiles', doc_id=None, data=p_data)

        # 标记激活码为已使用
        code_data['status'] = 'used'
        code_data['usedBy'] = openid
        code_data['usedAt'] = now_str
        code_doc.data = code_data
        code_doc.save()

        return vip_duration

    # 使用重试机制（防 SQLite 锁冲突）
    try:
        result_duration = _db_write_with_retry(_do_activate)
    except (IntegrityError, OperationalError) as e:
        return JsonResponse({'code': 50001, 'message': f'激活失败，请稍后重试：{str(e)}'}, status=500)

    # 清除用户统计缓存
    from django.core.cache import cache
    cache.delete('admin:user_stats:all')

    return JsonResponse({
        'code': 0,
        'message': '激活成功！您已获得 VIP 权限',
        'data': {
            'vip': True,
            'vipDuration': result_duration,
        }
    })
