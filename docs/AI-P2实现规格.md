# AI P2 功能实现规格（团队共享契约）

> 本文件是 P2 实施的唯一契约来源。后端、管理端前端、小程序端前端三方必须严格对齐本文件的接口签名。

## 一、P2 五个功能与职责划分

| # | 功能 | 端 | 后端服务类 | admin 路由 | 小程序路由 |
|---|------|----|-----------|-----------|-----------|
| 8 | 知识库 RAG 问答 | 小程序 + 管理端 | `KnowledgeRAGService` | 索引重建/统计 | `POST /api/ai/kb-ask/` |
| 9 | 题目自动标签推荐 | 管理端 | `AutoTagService` | 推荐/批量应用 | — |
| 10 | Excel 导入智能校验 | 管理端 | `ExcelValidateService` | 校验（异步任务） | — |
| 11 | 用户学习报告 | 小程序 | `LearningReportService` | — | `GET/POST /api/ai/report/` |
| 12 | 智能客服/答疑 | 小程序 | `CustomerService` | — | `POST /api/ai/cs-chat/` |

**技术前提（复用 P0/P1 基础设施，零新增第三方依赖）：**
- LLM 调用：`ai_services._call_llm` / `AIServiceBase.call_llm_with_fallback`
- 缓存：`AICacheManager`（content_hash = SHA-256[:16]）
- 异步：`AIJobManager`（threading.Thread）
- Prompt：`ai_prompts.PromptBuilder`
- 小程序鉴权：`@csrf_exempt` + `X-Openid` 请求头

---

## 二、后端实现规格（`backend/adminapi/`）

### 2.1 `ai_services.py` —— 新增 5 个服务类

所有服务类继承 `AIServiceBase`。`FUNCTION_MODEL_MAP` 新增映射：
```python
FUNCTION_MODEL_MAP = {
    ...  # 保留 P0/P1 全部
    'kb_qa': 'standard',
    'auto_tag': 'standard',
    'excel_validate': 'complex',
    'learning_report': 'complex',
    'cs_chat': 'standard',
}
```

#### ① KnowledgeRAGService（知识库 RAG 问答）
```python
class KnowledgeRAGService(AIServiceBase):
    COLLECTION = 'ai_kb_answers'      # 缓存集合（复用，非新建 Document 表）
    TOP_K = 5
    MIN_SCORE = 0.05
    # 语料来源：collection='knowledgebase' 全量文档

    @classmethod
    def build_corpus(cls) -> list:
        """读取 knowledgebase 全部文档，构建 chunk 列表。
        每个 chunk = {'doc_id','title','category','type','text','tokens'}
        text = title + '\n' + summary + '\n' + ' '.join(toc 各级标题)
        """

    @classmethod
    def tokenize(cls, text) -> list:
        """纯 Python 中文分词：正则提取中文 2-gram + 英文/数字单词，全部小写，去停用词。"""

    @classmethod
    def retrieve(cls, question, top_k=5) -> list:
        """TF-IDF 简化打分（零依赖）。返回 [{'doc_id','title','text','score'}]，按 score 降序，
        score < MIN_SCORE 的过滤掉。语料为空时返回 []。"""

    @classmethod
    def ask(cls, question) -> dict:
        """主入口（同步）。
        1) 归一化问题（strip + 去空白）→ compute_hash(['kb', q_norm])
        2) 查缓存 AICacheManager.get(COLLECTION, doc_id=hash, field='answer')
        3) 命中 → 直接返回，标记 cached=True
        4) 未命中 → retrieve → 构造 prompt → call_llm_with_fallback(tier='standard')
        5) 存缓存 → 返回
        返回: {'answer': str(markdown), 'sources': [{'doc_id','title'}], 'cached': bool}
        无检索结果时: {'answer': '知识库中暂未找到相关内容...', 'sources': [], 'cached': False}
        """

    @classmethod
    def rebuild_index(cls) -> dict:
        """清空 ai_kb_answers 全量缓存。返回 {'cleared': n, 'corpus_size': m}"""

    @classmethod
    def get_stats(cls) -> dict:
        """返回 {'corpus_size': 知识库文档数, 'cache_count': 缓存条目数}"""
```

#### ② AutoTagService（题目自动标签）
```python
class AutoTagService(AIServiceBase):
    @classmethod
    def suggest_tags(cls, question_doc) -> dict:
        """为单题推荐标签。优先复用 question_doc.data['ai_analysis']['suggested_tags']，
        无则调用 LLM（build_auto_tag_prompt）。
        返回 {'question_id': str, 'suggested_tags': [{'name','category','confidence'}], 'source': 'cache'|'ai'}"""

    @classmethod
    def suggest_batch(cls, question_ids, job_id=None) -> str | dict:
        """批量推荐（10 题/批，共享 system prompt）。有 job_id 时写入 AIJobManager 进度并返回 job_id；
        否则同步返回 {'items': [...], 'total': n}"""

    @classmethod
    def apply_tags(cls, question_id, tag_names) -> dict:
        """按名称应用标签：
        - 对每个 name，在 Tag 表按 name 查（同 category 优先），不存在则以 category='knowledge' 创建
        - 写 QuestionTag 绑定（unique_together）+ 同步 doc.data['tag_ids']
        返回 {'applied': n, 'tag_ids': [...]}"""
```

#### ③ ExcelValidateService（Excel 智能校验）
```python
class ExcelValidateService(AIServiceBase):
    BATCH_SIZE = 20

    @classmethod
    def validate_rows(cls, rows, qtype, job_id=None) -> dict:
        """AI 校验导入数据质量。
        rows: list[dict]（每行 = 表头映射后的字典）
        分批（20 行/批）调用 LLM，汇总：
        返回 {'total': n, 'valid_count': n, 'error_count': n,
              'errors': [{'row': i, 'field': str, 'level': 'error'|'warning', 'message': str, 'suggestion': str}],
              'corrections': [{'row': i, 'field': str, 'original': str, 'corrected': str}],
              'column_mapping': {'源列': '目标字段'}}
        LLM 失败时降级返回基础结构（不抛异常）。"""
```

#### ④ LearningReportService（用户学习报告）
```python
class LearningReportService(AIServiceBase):
    COLLECTION = 'ai_reports'
    MIN_RECORDS = 5
    TYPES = ('weekly', 'monthly', 'pre_exam')

    @classmethod
    def _period_range(cls, report_type) -> tuple:
        """返回 (period_key, start_date, end_date) 字符串。
        weekly → 近 7 天（period_key='YYYY-WW'）；
        monthly → 近 30 天（period_key='YYYY-MM'）；
        pre_exam → 近 14 天（period_key='pre-YYYYMMDD'）"""

    @classmethod
    def aggregate(cls, openid, report_type) -> dict:
        """聚合周期内 historys + notes：
        {'record_count','avg_accuracy','accuracy_trend':[{'date','accuracy'}],
         'subject_stats':{...}, 'wrong_count', 'study_days'}"""

    @classmethod
    def generate(cls, openid, report_type, job_id=None) -> dict:
        """异步/同步生成：aggregate → LLM → 写入 ai_reports（doc_id='report-{openid}-{type}-{period}'）
        返回报告 dict {'_openid','report_type','period','content_md','summary','highlights','suggestions','generated_at'}"""

    @classmethod
    def get_report(cls, openid, report_type='weekly') -> dict | None:
        """读取该用户该类型最新一份报告。"""
```

#### ⑤ CustomerService（智能客服）
```python
class CustomerService(AIServiceBase):
    @classmethod
    def _load_faq(cls) -> str:
        """从 app_config doc_id='rules' 读取平台规则文本（读不到用内置默认 FAQ）。"""

    @classmethod
    def chat(cls, openid, message, history=None) -> dict:
        """实时对话（无持久化）。
        history: [{'role':'user'|'assistant','content':str}]（最多取最近 6 条）
        → 构造 messages（system 含 FAQ + 知识库 top3 摘要）→ LLM
        返回 {'reply': str, 'suggestions': [str]}（suggestions 为 3 条推荐追问）"""
```

### 2.2 `ai_prompts.py` —— 新增 5 个 system prompt + 5 个 build 方法
新增 system prompts key：`kb_qa`、`auto_tag`、`excel_validate`、`learning_report`、`cs_chat`
新增 build 方法：
```python
build_kb_qa_prompt(question, contexts) -> str          # contexts: [{'title','text'}]
build_auto_tag_prompt(question_title, content_md, qtype) -> str
build_excel_validate_prompt(rows, qtype) -> str        # rows: list[dict]
build_learning_report_prompt(stats, report_type) -> str
build_cs_chat_prompt(message, faq_text, kb_context) -> str
```

### 2.3 `views_ai.py` —— 新增视图函数

**管理端（`@require_perms` 鉴权）：**

| 视图 | 方法/路径 | 权限 | 说明 |
|------|----------|------|------|
| `kb_rebuild` | POST `/api/admin/ai/kb/rebuild/` | `ai.config` | 重建知识库索引 |
| `kb_stats` | GET `/api/admin/ai/kb/stats/` | `ai.config` | 索引统计 |
| `question_suggest_tags` | POST `/api/admin/ai/questions/<doc_id>/suggest-tags/` | `ai.analyze` | 单题标签推荐 |
| `question_auto_tag_batch` | POST `/api/admin/ai/questions/auto-tag/` | `ai.analyze` | 批量（异步，body `{question_ids: [...]}`，返回 job_id） |
| `excel_validate` | POST `/api/admin/ai/excel-validate/` | `question.import` | 异步校验（body `{rows:[...], qtype:'single'}`，返回 job_id） |
| `question_apply_tags` | PUT `/api/admin/ai/questions/<doc_id>/tags/` | `ai.analyze` | 按标签名应用（body `{tag_names:[...]}`，返回 `{applied:n, tag_ids:[...]}`），调用 `AutoTagService.apply_tags` |

**小程序端（`@csrf_exempt` + X-Openid 鉴权 + `_check_ai_rate_limit_custom` 限流）：**

| 视图 | 方法/路径 | 限流 | 说明 |
|------|----------|------|------|
| `kb_ask` | POST `/api/ai/kb-ask/` | 20 次/天 | body `{question}` → `KnowledgeRAGService.ask` |
| `learning_report` | GET `/api/ai/report/?type=weekly`、POST `/api/ai/report/` | POST 2 次/天 | GET 取最新报告；POST 异步生成（返回 job_id；记录不足返回提示） |
| `cs_chat` | POST `/api/ai/cs-chat/` | 30 次/天 | body `{message, history}` → `CustomerService.chat` |

> 返回统一使用 `ok(data, msg)` / `fail(ErrorCode.X, msg)`（来自 `.responses`）。

### 2.4 路由注册
- `adminapi/urls.py`：新增 5 条 admin 路由（见 2.3 表格）
- `core/urls.py`：新增 3 条小程序路由（`ai/kb-ask/`、`ai/report/`、`ai/cs-chat/`），与现有 `ai/review-plan/` 同模式

### 2.5 `settings.py`
`AI_FEATURE_CONFIG_DEFAULTS` 新增 5 条：
```python
'kb_qa':           {'enabled': True, 'model': '', 'temperature': 0.3, 'max_tokens': 1500},
'auto_tag':        {'enabled': True, 'model': '', 'temperature': 0.3, 'max_tokens': 800},
'excel_validate':  {'enabled': True, 'model': '', 'temperature': 0.2, 'max_tokens': 3000},
'learning_report': {'enabled': True, 'model': '', 'temperature': 0.7, 'max_tokens': 3000},
'cs_chat':         {'enabled': True, 'model': '', 'temperature': 0.5, 'max_tokens': 1200},
```

### 2.6 `core/views.py`
```python
ALLOWED_COLLECTIONS = {..., 'ai_kb_answers', 'ai_reports'}
PRIVATE_COLLECTIONS = {..., 'ai_reports'}   # 学习报告为用户私有数据
```

### 2.7 权限点
**不新增权限点**，复用现有：`ai.config`（知识库索引）、`ai.analyze`（标签推荐）、`question.import`（Excel 校验）、`ai.report`（学习报告管理）、`ai.recommend`（推荐类）。

---

## 三、管理端前端规格（`web-admin/`）

### 3.1 新增页面

#### `src/views/AIAutoTag.vue`（题目自动标签）
- 题目列表（分页，复用 `resource('questions')` 或 `http.get('/questions/', {params})`）
- 每行「AI 推荐标签」按钮 → `aiApi.suggestQuestionTags(id)` → 弹出标签选择（多选，预勾选推荐项）
- 「应用」→ `aiApi.applyQuestionTags`（后端用 apply_tags，路径见 3.2）
- 顶部「批量推荐」→ 选中多题 → `aiApi.autoTagBatch(ids)` → 轮询 `aiApi.jobStatus(jobId)`
- 使用 Element Plus（el-table / el-dialog / el-tag）+ 现有 `useResource` 或直接 http

#### `src/views/AIExcelValidate.vue`（Excel 智能校验）
- 文件上传（el-upload，接受 .xlsx）+ 题型选择（single/multiple/judge/fill/qa）
- 「开始校验」→ 前端解析 Excel（复用 Import.vue 的上传方式：直接 multipart 上传到 `/questions/import/excel/`？**不**——改为：先本地把 Excel 转 rows 不可行）
- **实现方式**：新增后端接口 `POST /api/admin/ai/excel-validate/upload/` 不要求——直接复用现有 `importApi.importExcel` 的解析逻辑不可行。
  **简化方案（本规格采用）**：页面提供一个 JSON/表格粘贴区（el-input textarea，粘贴多行「题干|答案|解析」或 JSON 数组），前端转换为 rows 数组 → `aiApi.excelValidate({rows, qtype})` → 异步 job → 结果表格展示（valid/error/warning 分级，纠错建议）
- 结果区：统计卡片（总行数/通过/错误/警告）+ el-table（行号/字段/级别/问题/建议）+ 「复制修正后数据」

### 3.2 `src/api/index.js`
`aiApi` 新增方法：
```js
// P2: 知识库
kbRebuild: () => http.post('/ai/kb/rebuild/'),
kbStats: () => http.get('/ai/kb/stats/'),
// P2: 题目自动标签
suggestQuestionTags: (docId) => http.post(`/ai/questions/${docId}/suggest-tags/`),
autoTagBatch: (questionIds) => http.post('/ai/questions/auto-tag/', { question_ids: questionIds }),
applyQuestionTags: (docId, data) => http.put(`/ai/questions/${docId}/tags/`, data),
// P2: Excel 校验
excelValidate: (data) => http.post('/ai/excel-validate/', data),
```
> **勘误（2026-09-12 修订）**：`applyQuestionTags` 的最终后端路由为 `PUT /api/admin/ai/questions/<doc_id>/tags/`（见 2.3 新增行 `question_apply_tags`），接收 `{tag_names: [...]}`，调用 `AutoTagService.apply_tags`（按名称匹配已有标签、缺失则创建并绑定）。
> 注意：P0 已有的 `PUT /api/admin/questions/<doc_id>/tags/`（`tag_ids` 全量替换）是**另一条**路由，二者不要混用。

### 3.3 `src/router/index.js`
新增 2 条路由（`group: 'system'`）：
```js
{ path: 'ai-auto-tag',  name: 'ai-auto-tag',  component: AIAutoTag.vue,  meta: { title: 'AI自动标签', icon: PriceTag, perm: 'ai.analyze', group: 'system' } },
{ path: 'ai-excel-validate', name: 'ai-excel-validate', component: AIExcelValidate.vue, meta: { title: 'AI数据校验', icon: CircleCheck, perm: 'question.import', group: 'system' } },
```

---

## 四、小程序端前端规格（`miniprogram/`）

### 4.1 新增 3 个页面

#### `pages/ai-qa/index.*`（知识库智能问答）
- 顶部说明 + 消息列表（用户气泡右、AI 气泡左，AI 气泡内渲染 Markdown）
- 底部输入框 + 发送按钮
- AI 消息下方展示「来源」标签（sources）
- 首次进入显示 3 条「推荐问题」快捷按钮
- 调用 `api.aiKbAsk(question)`

#### `pages/ai-report/index.*`（学习报告）
- 顶部 Tab 切换：周报 / 月报 / 考前报告
- 报告卡片：Markdown 渲染（`utils/markdown.js`）
- 「生成报告」按钮 → `api.aiGenerateLearningReport(type)` → 轮询 `api.aiJobStatus(jobId)`
- 无报告时 empty 状态引导

#### `pages/ai-service/index.*`（智能客服）
- 对话界面（气泡风格同 ai-qa）
- 顶部常见问题快捷入口（3~4 条：如何开始练习？/ 错题怎么复习？/ 如何查看学习报告？/ 账号问题）
- 发送 → `api.aiCsChat(message, history)`；回复下方展示 suggestions 快捷追问
- 底部「提交反馈」按钮（可选，跳转 feedback，若无页面则 wx.showToast）

### 4.2 `utils/api.js` 新增方法（必须加入 module.exports）
```js
function aiKbAsk(question) { return request('POST', '/ai/kb-ask/', { question: question }); }
function aiLearningReport(type) { return request('GET', '/ai/report/?type=' + (type || 'weekly')); }
function aiGenerateLearningReport(type) { return request('POST', '/ai/report/', { type: type || 'weekly' }); }
function aiCsChat(message, history) { return request('POST', '/ai/cs-chat/', { message: message, history: history || [] }); }
```

### 4.3 `app.json`
`pages` 数组新增（保持顺序在现有 P1 页面之后）：
```
"pages/ai-qa/index",
"pages/ai-report/index",
"pages/ai-service/index"
```

### 4.4 入口卡片
- `pages/mine/index`（或 home）：新增「AI 助手」区块，3 个入口指向上述 3 个页面
- 入口修改要最小化，仅新增块，不改动既有逻辑

---

## 五、验收标准

| 验收项 | 标准 |
|--------|------|
| Django check | `manage.py check` → 0 issues |
| P0 回归 | `python test_ai_p0.py` → 90/90 PASS |
| P1 回归 | `python test_ai_p1.py` → 65/65 PASS |
| P2 新测试 | `python test_ai_p2.py` → 全部 PASS（服务类/路由/配置/集合白名单/Prompt） |
| Vite build | `npx vite build` → exit 0 |
| 小程序语法 | 各新增 .js/.json 无语法错误（node --check） |

**运行环境**：后端 Python = `python`；前端构建用 `cd web-admin && npx vite build`。
