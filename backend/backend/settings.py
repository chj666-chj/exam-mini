"""
Django settings —— 考试宝小程序后端

定位：复刻微信云开发数据库语义的最小 Django 后端。
- sqlite3 存储，零外部依赖
- 通用文档模型（core.Document），模拟云数据库集合
- 后续正式开发时可替换为具体业务模型（题目/考试/答题记录等）

部署安全配置通过环境变量注入，本地开发有默认值。
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ---- 核心安全配置（从环境变量读取，本地开发有默认值）----
SECRET_KEY = os.environ.get(
    'EXAM_SECRET_KEY',
    'django-insecure-exam-mini-local-dev-only-change-me'
)
DEBUG = os.environ.get('EXAM_DEBUG', 'True').lower() in ('true', '1', 'yes')
ALLOWED_HOSTS = os.environ.get('EXAM_ALLOWED_HOSTS', '*').split(',')

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'core',      # 小程序端兼容层（复刻微信云开发语义）
    'adminapi',  # Web 管理端接口（统一响应规范 + RBAC）
]

MIDDLEWARE = [
    'django.middleware.common.CommonMiddleware',
    'core.middleware.ApiCorsMiddleware',  # 小程序本地调试用 CORS 支持
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {'context_processors': []},
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            # SQLite 并发写入优化（修复 "database is locked" 错误）：
            #   WAL 模式 —— 允许多读 + 单写并发，读写互不阻塞
            #   busy_timeout=5000 —— 写冲突时等待 5 秒而非立即报错
            #   synchronous=NORMAL —— WAL 模式下安全且更快的同步策略
            # 场景：交卷时多个 addNote + addHistory 同时 POST，并发写入导致锁冲突
            'init_command': (
                'PRAGMA journal_mode=WAL;'
                'PRAGMA busy_timeout=5000;'
                'PRAGMA synchronous=NORMAL;'
            ),
        },
    }
}

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_TZ = True

STATIC_URL = 'static/'

# 题目图片上传（管理端 /api/admin/upload/）
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---- 缓存配置（生产环境用 Redis，本地开发用 LocMem）----
REDIS_URL = os.environ.get('REDIS_URL', '')
if REDIS_URL:
    try:
        import redis  # noqa: F401
        CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                'LOCATION': REDIS_URL,
            }
        }
    except ImportError:
        # redis 包未安装，降级到 LocMem
        CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                'LOCATION': 'kaoshibao-fallback',
            }
        }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'kaoshibao-dev',
        }
    }

# ---- 考试宝业务配置 ----
# 数据源目录（原仓库 data/*.jsonl）—— 通过环境变量配置，默认使用项目内相对路径
EXAM_DATA_DIR = os.environ.get('EXAM_DATA_DIR', str(BASE_DIR / 'data'))
# 登录接口返回的演示 openid（前端无真实微信鉴权时使用）
# login 视图会优先返回 historys 集合中记录数最多的 openid，以便演示数据可见
DEV_DEFAULT_OPENID = 'dev-openid-0001'

# 小程序端写权限校验：True 表示写入私有集合（答题记录/错题/用户资料等）
# 必须携带 login 获取的 openid，且只能修改本人数据（对齐云开发集合权限）。
# 仅在需要裸数据调试（如 curl 直接写入）时临时设为 False。
EXAM_REQUIRE_OPENID_FOR_WRITE = True

# ---- 管理端配置 ----
# 登录令牌有效期（小时）
ADMIN_TOKEN_TTL_HOURS = int(os.environ.get('ADMIN_TOKEN_TTL_HOURS', '12'))
# 管理端默认账号（由 python manage.py init_admin 创建，仅本地演示用）
ADMIN_DEFAULT_USERNAME = os.environ.get('ADMIN_DEFAULT_USERNAME', 'admin')
ADMIN_DEFAULT_PASSWORD = os.environ.get('ADMIN_DEFAULT_PASSWORD', 'admin123')

# ---- AI 配置默认值 ----
AI_CONFIG_DEFAULTS = {
    'apiUrl': 'https://api.openai.com/v1/chat/completions',
    'apiKey': '',
    'model': 'gpt-4o-mini',
    'systemPrompt': '你是一个专业的备考文章写作助手，请根据用户给出的主题，撰写一篇结构清晰、内容充实的 Markdown 格式备考文章。',
    'temperature': 0.7,
    'maxTokens': 2000,
    'enabled': False,
}

# ---- AI 功能级配置默认值 ----
# 各功能可独立配置模型、温度、最大 token 数；空 model 表示使用 AI_CONFIG_DEFAULTS 中的全局模型
AI_FEATURE_CONFIG_DEFAULTS = {
    'question_analyze': {'enabled': True, 'model': '', 'temperature': 0.3, 'max_tokens': 2000},
    'exam_compose': {'enabled': True, 'model': '', 'temperature': 0.5, 'max_tokens': 2000},
    'ai_grade': {'enabled': True, 'model': 'gpt-4o', 'temperature': 0.2, 'max_tokens': 4000},
    'exam_analyze': {'enabled': True, 'model': '', 'temperature': 0.7, 'max_tokens': 4000},
    'learning_profile': {'enabled': True, 'model': '', 'temperature': 0.7, 'max_tokens': 4000},
    'review_recommend': {'enabled': True, 'model': '', 'temperature': 0.3, 'max_tokens': 1000},
    'article_enhance': {'enabled': True, 'model': '', 'temperature': 0.7, 'max_tokens': 2000},
    # ---- P2 级功能 ----
    'kb_qa':           {'enabled': True, 'model': '', 'temperature': 0.3, 'max_tokens': 1500},
    'auto_tag':        {'enabled': True, 'model': '', 'temperature': 0.3, 'max_tokens': 800},
    'excel_validate':  {'enabled': True, 'model': '', 'temperature': 0.2, 'max_tokens': 3000},
    'learning_report': {'enabled': True, 'model': '', 'temperature': 0.7, 'max_tokens': 3000},
    'cs_chat':         {'enabled': True, 'model': '', 'temperature': 0.5, 'max_tokens': 1200},
}

# ---- AI 多模型配置数量上限 ----
# 模型条目存储于 ai_models 集合：
#   global —— 管理员在后台「AI 配置 → 模型列表」维护，全部用户可用；
#   user   —— 小程序用户自行添加（携带自己的 Key），仅本人可用。
AI_MODEL_LIMITS = {
    'global': 10,   # 最多添加的全局模型数量
    'user': 5,      # 每个小程序用户最多添加的模型数量
}

# ---- AI 超时与性能配置 ----
# 按模型分级设置 LLM 调用超时（秒），避免单一 60s 硬编码导致
# 简单任务等太久、复杂任务不够用
AI_LLM_TIMEOUTS = {
    'lite': 30,       # 复习推荐 / 自动标签等轻量任务
    'standard': 45,   # 题目解析 / 知识库问答 / 客服
    'complex': 90,    # 判卷 / 试卷分析 / 组卷 / 学习画像 / Excel校验 / 学习报告
    'default': 45,    # 未匹配分级时的兜底超时
}

# 重试间隔基数（秒）—— 指数退避：第1次等 2s，第2次等 4s，第3次等 8s
AI_LLM_RETRY_DELAY = 2

# LLM 最大重试次数（首次调用 + 此数值 = 总尝试次数）
AI_LLM_MAX_RETRIES = 2

# LLM 响应体最大字节数（防止超大响应导致 OOM）
AI_LLM_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB

# 批量操作整体超时（秒）—— 异步 Job 的最大执行时间
AI_JOB_TIMEOUT_SECONDS = 600  # 10 分钟

# 批量判卷并发度（同时调用 LLM 的线程数）
AI_BATCH_CONCURRENCY = 3

# 组卷候选题池上限（避免全量加载导致 prompt 爆炸）
# 注：预过滤后实际发送给 LLM 的候选题数通常远小于此值
AI_COMPOSE_MAX_CANDIDATES = 200

# 组卷 prompt 中候选题最大行数（超出截断，防止 prompt 过大导致 LLM 超时）
AI_COMPOSE_PROMPT_MAX_LINES = 200

# ---- 组卷分层随机采样配置 ----
# 采样比率：每种题型的候选采样数 = 用户需要的该题型题数 × 此比率
# 例如用户需要 10 道单选题，则从题库中随机采样 10 × 5 = 50 道作为候选
AI_COMPOSE_SAMPLE_RATIO = 5

# 每种题型的采样上限（即使题库中有 1000 道单选题，最多只采样此数）
AI_COMPOSE_SAMPLE_MAX_PER_QTYPE = 60

# 每种题型的采样下限（即使用户只需要 1 道题，也至少采样此数保证多样性）
AI_COMPOSE_SAMPLE_MIN_PER_QTYPE = 10

# 复习推荐错题加载上限
AI_REVIEW_MAX_NOTES = 200

# Excel 校验每批行数（合并 prompt，减少 LLM 调用次数）
AI_EXCEL_BATCH_SIZE = 20
