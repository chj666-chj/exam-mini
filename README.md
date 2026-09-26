# 考试宝（Exam Mini）

基于微信小程序的在线考试与备考平台，包含小程序前端、Django 后端和 Vue 3 管理后台，内置 AI 智能判卷、智能组卷、学习画像等 12 项 AI 功能。

## 技术栈

| 端 | 技术 | 说明 |
|---|---|---|
| 小程序前端 | 微信原生小程序 | 21 个业务页面，复刻云开发语义的 API 兼容层 |
| 后端 | Django + SQLite | 通用文档模型模拟云数据库集合，零外部数据库依赖 |
| 管理后台 | Vue 3 + Vite + Element Plus + ECharts | 数据看板、题库管理、AI 配置、批量导入 |
| AI 服务 | 纯 Python TF-IDF + urllib LLM | 零新增依赖，支持多模型配置与分级超时 |

## 目录结构

```
├── miniprogram/          # 微信小程序前端
│   ├── app.js            # 启动时调用 /api/login 获取 openid
│   ├── app.json          # 21 个业务页面
│   ├── utils/api.js      # 云开发兼容层：wx.cloud -> wx.request(Django)
│   └── pages/            # 首页、答题、错题本、复习、收藏等
├── backend/              # Django 后端
│   ├── manage.py
│   ├── backend/          # settings / urls / wsgi
│   ├── core/             # 小程序端兼容层（云开发语义 + 写权限校验）
│   ├── adminapi/         # Web 管理端接口（统一响应信封 + RBAC + AI 服务）
│   └── .env.example      # 环境变量配置模板
├── web-admin/            # Vue 3 管理后台
│   ├── src/views/        # 数据看板、题库、标签、导入、AI 配置等
│   ├── src/components/   # MarkdownRenderer 等通用组件
│   └── vite.config.js    # dev 代理 /api -> 127.0.0.1:8000
├── docs/                 # 接口规范、AI 架构设计、系统设计文档
└── README.md
```

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+
- 微信开发者工具

### 1. 启动后端

```bash
cd backend

# 安装依赖
pip install django

# 初始化数据库
python manage.py migrate

# 创建默认管理员账号
python manage.py init_admin

# 导入示例题库数据（可选）
python manage.py load_exam_data

# 启动开发服务器
python manage.py runserver 127.0.0.1:8000
```

### 2. 启动管理后台

```bash
cd web-admin
npm install
npm run dev    # http://127.0.0.1:5173
```

默认管理员账号通过 `init_admin` 命令创建，用户名和密码可通过环境变量配置（见下文）。

### 3. 打开小程序

1. 打开微信开发者工具
2. 导入项目，目录选择 `miniprogram/`
3. AppID 选择「测试号/游客模式」（项目内置 `touristappid`，无需注册）
4. 详情 -> 本地设置 -> 勾选「不校验合法域名」（本地开发必须）

## 环境变量配置

复制 `backend/.env.example` 为 `backend/.env` 并按需修改：

```bash
# Django 安全配置（生产环境必须修改）
EXAM_SECRET_KEY=your-random-secret-key-at-least-50-chars
EXAM_DEBUG=False
EXAM_ALLOWED_HOSTS=your-domain.com

# 管理端配置
ADMIN_DEFAULT_USERNAME=admin
ADMIN_DEFAULT_PASSWORD=change-me-in-production
ADMIN_TOKEN_TTL_HOURS=12

# 缓存配置（留空使用 LocMem）
REDIS_URL=

# 题库数据目录（默认 backend/data/）
EXAM_DATA_DIR=/path/to/your/data
```

> 本地开发无需配置 `.env` 文件，所有变量有安全的默认值。

## 核心功能

### 小程序端

| 功能 | 说明 |
|---|---|
| 题库浏览 | 按科目分类，支持单题模式与列表模式 |
| 在线答题 | 逐题作答 / 整卷作答，倒计时，断点续答 |
| 错题本 | 自动收录错题，支持复习与标注 |
| 答题记录 | 历史成绩、正确率统计 |
| 收藏夹 | 题目 / 文章 / 知识点收藏 |
| 激活码 | VIP 功能激活 |

### 管理后台

| 模块 | 说明 |
|---|---|
| 数据看板 | 用户/答题/错题/题目统计，趋势图，科目分布，活跃用户 Top10 |
| 题库管理 | 六种题型编辑器（单选/多选/判断/填空/简答/案例），Markdown 支持 |
| 批量导入 | Excel/CSV 导入，校验/去重/异步任务 |
| AI 配置 | 多模型管理，功能级配置，超时分级，API Key 脱敏 |
| 标签管理 | 标签 CRUD，AI 自动标签推荐 |
| 用户管理 | 用户列表、详情、编辑、数据清理 |
| 系统管理 | 管理员 CRUD、角色权限、操作日志审计 |

### AI 功能（12 项）

| 功能 | 说明 |
|---|---|
| 题目解析 | AI 分析题目考点与难度 |
| 智能组卷 | 三阶段定向组卷，支持 10 万+ 题库 |
| 智能判卷 | 主观题 AI 评分 + 人工复核 |
| 试卷分析 | 整卷难度/覆盖度评估 |
| 学习画像 | 个性化学习诊断 |
| 复习推荐 | 基于错题的智能推荐 |
| 文章增强 | AI 辅助备考文章写作 |
| 知识库问答 | RAG 检索增强问答 |
| 自动标签 | AI 推荐题目标签 |
| Excel 校验 | 批量数据 AI 校验 |
| 学习报告 | 个性化学习报告生成 |
| 客服对话 | AI 在线客服 |

## API 概览

### 小程序端（复刻云数据库语义）

| 接口 | 说明 |
|---|---|
| `POST /api/login/` | 模拟云函数 login，返回 openid |
| `GET /api/collections/<name>/?field=value` | 集合查询，等值过滤 |
| `GET /api/collections/<name>/<id>/` | 按 _id 取文档 |
| `POST /api/collections/<name>/` | 新增文档（X-Openid 头自动注入） |
| `PUT/DELETE /api/collections/<name>/<id>/` | 更新 / 删除 |

### 管理端（统一响应信封 + Bearer Token 鉴权）

| 接口 | 说明 |
|---|---|
| `POST /api/admin/auth/login/` | 管理员登录 |
| `GET /api/admin/dashboard/` | 数据看板 |
| `GET/POST /api/admin/questions/` | 题库 CRUD |
| `POST /api/admin/import/` | 批量导入 |
| `GET/POST /api/admin/ai-config/` | AI 配置 |
| `POST /api/admin/ai/analyze/` | AI 题目解析 |
| `POST /api/admin/ai/grade/` | AI 智能判卷 |

详细接口规范、错误码与权限点见 `docs/` 目录。

## 安全说明

- 所有敏感配置（SECRET_KEY、数据库、API Key 等）通过环境变量注入，不硬编码在源码中
- AI API Key 在管理端传输和存储时自动脱敏（仅保留末 4 位）
- 小程序端写权限校验：私有集合操作必须携带 openid
- 管理端采用 RBAC 权限模型 + Bearer Token 鉴权
- AI 配置中 API URL 校验拒绝内网/回环地址

## 开发说明

- 后端使用 SQLite + WAL 模式，支持并发写入（busy_timeout + 重试机制）
- 小程序 API 兼容层 (`utils/api.js`) 支持链式调用和 Promise 两种风格
- 管理后台 Markdown 渲染支持 LaTeX 公式（`$$...$$` / `$...$`）
- 判题逻辑统一在 `miniprogram/utils/judge.js`（SSOT，纯函数）

## License

MIT
