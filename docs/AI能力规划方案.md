# 考试宝 · AI 能力规划方案（完整版）

> **文档版本**：v1.0  
> **日期**：2026-09-12  
> **产出方**：软件开发团队（产品经理许清楚 + 架构师高见远 + 交付总监齐活林）  
> **项目**：考试宝备考平台 AI 能力系统性规划与实施方案

---

## 目录

- [一、方案概览](#一方案概览)
- [二、AI 功能全景（12 个模块）](#二ai-功能全景12-个模块)
- [三、各模块详细方案](#三各模块详细方案)
- [四、AI 结果存储与复用策略](#四ai-结果存储与复用策略)
- [五、Token 成本控制措施](#五token-成本控制措施)
- [六、技术架构设计](#六技术架构设计)
- [七、异步任务方案](#七异步任务方案)
- [八、权限点扩展与 API 路由设计](#八权限点扩展与-api-路由设计)
- [九、数据结构设计](#九数据结构设计)
- [十、实现优先级与任务分解](#十实现优先级与任务分解)
- [十一、潜在风险与注意事项](#十一潜在风险与注意事项)
- [十二、待确认问题与架构建议](#十二待确认问题与架构建议)

---

## 一、方案概览

### 1.1 项目现状

| 维度 | 现状 |
|------|------|
| **后端** | Django + SQLite，通用 JSON 文档模型 `Document(collection, doc_id, data)` |
| **管理后台** | Vue 3 + Vite + Element Plus + ECharts，27 个权限点，3 个内置角色 |
| **小程序** | 微信原生小程序，40+ 页面，覆盖考试/练习/错题/知识库/文章 |
| **现有 AI** | `_call_llm()` LLM 调用引擎、AI 配置管理、AI 辅助写作（限流）、AI 判卷预留接口 |

### 1.2 产品目标

| 编号 | 目标 | 衡量指标 |
|------|------|----------|
| G1 | **提升内容生产效率** 3-5 倍 | 单题解析 5min→30s；组卷 30min→5min |
| G2 | **提升学习效果** | 用户周活 +20%；错题复习覆盖率 ≥80%；平均正确率 +15% |
| G3 | **降低运营成本** | 主观题判卷人工干预率 <30%；Excel 导入纠错成功率 ≥90% |

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **最大化复用** | 复用已有 `_call_llm()` 引擎、`ai_config` 配置、`ImportJob` 异步模式、RBAC 权限体系 |
| **最小化侵入** | AI 能力作为独立服务层叠加，不改动核心数据模型和已有业务逻辑 |
| **缓存优先** | 所有 AI 结果持久化缓存，内容未变更时不重复调用 LLM |
| **渐进式上线** | P0→P1→P2 分批交付，每个功能可独立开关 |
| **零新增依赖** | 全部基于 Python 标准库 + 已有框架依赖，无需安装新包 |
| **安全可控** | 学生数据送入 LLM 前脱敏，AI 生成内容标注来源，人工复核关键环节 |

---

## 二、AI 功能全景（12 个模块）

### 2.1 优先级总览

| 优先级 | # | AI 功能 | 核心价值 | 实现难度 | Token 成本 | 依赖 |
|:---:|:---:|---------|:---:|:---:|:---:|------|
| **P0** | 1 | AI 题目解析 | ★★★★★ 基础设施 | 中 | 中（可缓存） | 无 |
| **P0** | 2 | AI 智能组卷 | ★★★★★ 高频场景 | 中 | 低（先筛选后优化） | 题库有标签/解析数据 |
| **P0** | 3 | AI 主观题判卷 | ★★★★★ 填充预留接口 | 中 | 高（每份答卷调用） | 题目需预设 rubric |
| **P1** | 4 | AI 试卷分析 | ★★★★☆ 依赖数据积累 | 较高 | 中 | ≥10 份答题记录 |
| **P1** | 5 | 错题复习推荐 | ★★★★☆ 考生留存 | 中 | 低（算法为主） | 答题历史积累 |
| **P1** | 6 | 答题记录分析 | ★★★★☆ 个性化指导 | 中 | 中 | 答题历史 + 标签体系 |
| **P1** | 7 | AI 文章撰写增强 | ★★★☆☆ 现有增强 | 低 | 中 | 复用现有接口 |
| **P2** | 8 | 知识库 RAG 问答 | ★★★★☆ 长期高价值 | 高 | 高（实时检索） | 知识库内容充足 |
| **P2** | 9 | 题目自动标签推荐 | ★★★☆☆ 效率提升 | 低 | 低 | 与题目解析协同 |
| **P2** | 10 | Excel 导入智能校验 | ★★★☆☆ 防错提效 | 中 | 中 | 增强现有 ImportJob |
| **P2** | 11 | 用户学习报告 | ★★★☆☆ 体验提升 | 中 | 中 | 答题历史积累 |
| **P2** | 12 | 智能客服/答疑 | ★★★☆☆ 降低客服成本 | 中 | 高（实时对话） | 客服知识库准备 |

### 2.2 建议实施路线图

```
Phase 1（P0，1-2 个月）
  └─ T01 基础设施层 → T02 题目解析 → T03 智能判卷 → 智能组卷
     （基础设施先行；判卷与组卷在 T01 完成后可并行）

Phase 2（P1，2-3 个月）
  └─ 试卷分析 → 答题分析 → 错题复习推荐 + AI 文章增强（并行）

Phase 3（P2，3-6 个月）
  └─ 题目自动标签 → Excel 智能校验 → 学习报告 → RAG 问答 → 智能客服
```

---

## 三、各模块详细方案

### 3.1 AI 题目解析模块（P0）

| 维度 | 内容 |
|------|------|
| **功能描述** | 管理员录入/导入题目后，AI 自动完成：① 知识点提取（映射到现有标签体系）；② 难度评估（easy/medium/hard + 1-10 分）；③ 题型识别（交叉验证 qtype）；④ 答案解析生成（Markdown 格式解题思路）；⑤ 推荐标签（4 类标签匹配 + 新标签建议）；⑥ 关键概念提取；⑦ 易错点提示 |
| **适用场景** | 新题录入一键解析；Excel 批量导入后自动解析；存量无解析题目批量补全 |
| **触发时机** | 单题编辑页"AI 解析"按钮（同步）；题库列表"批量 AI 解析"（异步）；Excel 导入完成后自动触发（异步） |
| **使用者** | 管理员 / 内容运营 |
| **存储策略** | 结果存入 `questions.data.ai_analysis` 字段，含 `content_hash` 缓存键 |
| **缓存命中** | `content_hash == SHA-256(content_md + qtype + options)[:16]` 匹配时复用 |
| **缓存失效** | 题目 `content_md` 或 `qtype` 编辑时自动清除；手动"重新分析"按钮强制清除 |
| **模型选择** | standard 级（gpt-4o-mini），temperature=0.3（解析需确定性） |
| **Token 控制** | 批量 10 题/次合并 prompt（节省 40%）；仅送 content_md + qtype（减少 30-50% 输入） |

### 3.2 AI 智能组卷（P0）

| 维度 | 内容 |
|------|------|
| **功能描述** | 管理员设定条件（科目、知识点、题型分布、难度比例、总分、题量），系统先 SQL 查询筛选候选题池，再 AI 优化组合（知识点覆盖均衡、难度梯度合理、避免重复）。支持"锁定部分题目 + AI 补全"混合模式。生成 draft 试卷可预览微调 |
| **适用场景** | 快速生成标准化试卷；按薄弱区定向组卷；模拟考试自动出卷 |
| **触发时机** | 管理后台"试卷管理 → AI 智能组卷"，异步执行（约 10-20 秒） |
| **使用者** | 管理员 / 教师 |
| **存储策略** | 组卷方案存入 `ai_jobs` collection（draft），确认后转为正式 `exam` 文档 |
| **Token 控制** | 先结构化查询筛选候选题池（仅送题号+难度+知识点摘要），输入从万级 token 降至千级（节省 80%） |
| **模型选择** | standard 级（gpt-4o-mini），temperature=0.5 |

### 3.3 AI 主观题智能判卷（P0）

| 维度 | 内容 |
|------|------|
| **功能描述** | 填充现有 `/api/admin/questions/<id>/ai-grade/` 预留接口，实现 qa/fill/multi_part 题型的 AI 自动评分。AI 根据 `ai_grading.rubric`（评分细则）和 `max_score`（满分），对比学生答案与参考答案，给出分数 + 评分依据 + 评语 + 置信度。Hybrid 模式：AI 初判 + 人工复核 |
| **适用场景** | 考试后批量自动判卷；日常练习即时反馈；高 stakes 考试 AI 辅助判卷 |
| **触发时机** | 学生交卷含主观题后自动触发（异步批量）；管理后台"待判卷"批量处理 |
| **使用者** | 系统（自动判卷）；管理员（复核与调整） |
| **存储策略** | 判卷结果存入 `historys.items[n].ai_grading`，含 `human_review` 复核字段 |
| **缓存命中** | `content_hash == SHA-256(question_md + answer_text + rubric)[:16]` |
| **人工复核** | `confidence < 0.7` 或 `score == 0/max_score` 自动标记"需人工复核" |
| **模型选择** | complex 级（gpt-4o），temperature=0.2（评分需一致性） |

### 3.4 AI 试卷分析（P1）

| 维度 | 内容 |
|------|------|
| **功能描述** | 针对已发布且有 ≥10 份答题记录的试卷，AI 生成：① 试卷质量评估（知识点覆盖度、难度分布、区分度分析、低质量题目预警）；② 学生作答分析（得分分布、常见错误模式、薄弱知识点聚类、改进建议） |
| **触发时机** | 试卷详情页"AI 分析"按钮（异步，约 15-30 秒） |
| **存储策略** | 存入 `exam.data.ai_analysis`，含 `content_hash` + `record_count` |
| **缓存失效** | 试卷配置变更 或 答题记录增长 ≥10% 时失效（懒失效） |
| **Token 控制** | 后端预聚合统计摘要（正确率/用时/难度分布），只送摘要不送全量记录（节省 70%） |

### 3.5 错题笔记智能复习推荐（P1）

| 维度 | 内容 |
|------|------|
| **功能描述** | 艾宾浩斯遗忘曲线算法为主 + AI 个性化优化为辅。算法生成基础复习清单（1天/2天/4天/7天/15天周期），AI 优化优先级和推荐理由。每日推荐 10-20 题，复习后动态调整 |
| **触发时机** | 小程序首页"今日复习"每日推送；错题本"AI 推荐复习"入口 |
| **存储策略** | 存入 `ai_review_plans` collection，`doc_id = review-{openid}-{YYYYMMDD}` |
| **缓存命中** | 同一用户同一天只生成一次（日缓存 100% 命中） |
| **限流** | 1 次/天/用户 |

### 3.6 答题记录智能分析（P1）

| 维度 | 内容 |
|------|------|
| **功能描述** | 汇总 historys 答题记录，AI 诊断：① 薄弱知识点（按标签维度正确率分析）；② 错误模式归纳（概念混淆/计算错误/审题不清等）；③ 能力画像雷达图；④ 定向练习推荐 |
| **触发时机** | 小程序"学习报告"页面查看（异步）；每周自动生成 |
| **存储策略** | 存入 `ai_learning_profile` collection，`doc_id = profile-{openid}` |
| **缓存失效** | 新增答题记录 ≥20 条 或 超过 7 天 → 重新分析 |
| **限流** | 1 次/7天/用户 |

### 3.7 AI 智能文章撰写增强（P1）

| 维度 | 内容 |
|------|------|
| **功能描述** | 在现有 `/api/ai/assist/` 基础上增强为完整创作工作流：选题推荐 → 大纲生成 → 正文生成 → 标题优化 → 摘要自动生成 → 配图建议。通过 `action` 参数区分 6 种操作 |
| **触发时机** | 管理后台"文章管理 → AI 写作"；小程序端保留增强辅助 |
| **存储策略** | 无持久化（无状态调用），结果直接返回前端，生成内容经审核流程（pending→published） |
| **限流** | 复用现有 10 次/60秒/用户 |

### 3.8-3.12 P2 补充场景概要

| # | 功能 | 触发端 | 核心价值 |
|:---:|------|:---:|------|
| 8 | 知识库 RAG 问答 | 小程序 | 自然语言提问 → 检索知识库 → LLM 生成回答 + 引用来源 |
| 9 | 题目自动标签推荐 | 管理端 | AI 根据题干自动推荐 4 类标签，与题目解析协同 |
| 10 | Excel 导入智能校验 | 管理端 | 导入前 AI 检查数据质量 + 自动纠错 + 智能列映射 |
| 11 | 用户学习报告 | 小程序 | 周报/月报/考前报告，AI 评语 + 进步轨迹 + 行动建议 |
| 12 | 智能客服/答疑 | 小程序 | 平台使用答疑 + 学习问题疏导 + 反馈收集 |

---

## 四、AI 结果存储与复用策略

### 4.1 存储策略总表

| # | AI 功能 | 存储位置 | 缓存命中条件 | 缓存失效策略 | 预期节省 |
|:---:|---------|---------|-------------|-------------|:---:|
| 1 | 题目解析 | `questions.data.ai_analysis` | `content_hash == hash(content_md + qtype)` | 题目编辑自动清除 | 70-90% |
| 2 | 智能组卷 | `ai_jobs` collection（draft） | 无缓存（条件不同） | 草稿 7 天清理 | — |
| 3 | 智能判卷 | `historys.items[n].ai_grading` | `content_hash == hash(question_md + answer + rubric)` | 题目/作答/标准变更 | 30-50% |
| 4 | 试卷分析 | `exam.data.ai_analysis` | `content_hash` 匹配 + 记录增长 <10% | 配置变更或记录增长超阈值 | 80-95% |
| 5 | 复习推荐 | `ai_review_plans` collection | 同一用户同一天 | 每日重新生成 | 100% |
| 6 | 答题分析 | `ai_learning_profile` collection | 7 天内 + 新增 <20 条 | 超时或新增超阈值 | 60-80% |
| 7 | 文章增强 | 无持久化 | — | — | — |

### 4.2 content_hash 计算规则

```python
import hashlib, json

def compute_content_hash(*fields) -> str:
    """将关键字段序列化后取 SHA-256 前 16 位作为缓存键。"""
    raw = json.dumps(fields, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]
```

### 4.3 缓存失效自动化机制

| 触发场景 | 机制 |
|---------|------|
| 题目内容编辑 | `views_data.py` 更新时，若 `content_md`/`qtype` 变更，自动置 `ai_analysis = null` |
| 批量导入覆盖 | ImportJob 覆盖题目时清除旧 `ai_analysis` |
| 答题记录新增 | 不影响已有缓存；新增超阈值时懒失效 |
| AI 配置模型变更 | `ai_config` 更新时 `cache_version + 1`，版本不匹配时失效 |
| 手动清除 | 管理端"重新分析"按钮 |

---

## 五、Token 成本控制措施

### 5.1 成本估算

> 以 gpt-4o-mini 价格（输入 $0.15/M, 输出 $0.60/M）估算

| 功能 | 单次成本 | 月频率 | 月成本 |
|------|:---:|------|:---:|
| 题目解析（单题） | ≈$0.0005 | 100 题/月（扣缓存） | ≈$0.05 |
| 题目解析（批量） | ≈$0.002 | 10 次/月 | ≈$0.02 |
| 智能组卷 | ≈$0.001 | 20 次/月 | ≈$0.02 |
| 主观题判卷 | ≈$0.0004 | 200 题/月 | ≈$0.08 |
| 试卷分析 | ≈$0.002 | 5 次/月 | ≈$0.01 |
| 复习推荐 | ≈$0.0005 | 900 次/月 | ≈$0.45 |
| 答题分析 | ≈$0.0015 | 120 次/月 | ≈$0.18 |
| 文章增强 | ≈$0.001 | 50 次/月 | ≈$0.05 |
| **P0 合计** | — | — | **≈$0.15** |
| **P0+P1 合计** | — | — | **≈$0.86** |

> **结论**：使用 gpt-4o-mini，月成本可控在 $1 以内；即使升级 gpt-4o（10 倍价格），月成本也在 $10 以内。

### 5.2 六大控制措施

| 措施 | 说明 | 预期效果 |
|------|------|:---:|
| **缓存复用** | 所有 AI 结果持久化，content_hash 匹配时直接返回 | 节省 70-90% |
| **批量处理** | 题目批量解析 10 题/次合并 prompt | 节省 40% |
| **分级模型** | lite/standard/complex 三级，判卷/分析用 gpt-4o，其余用 mini | 成本最优 |
| **限流配额** | 用户级 10次/60s + 功能级 30次/分钟 + 全局 1000次/天 | 防止滥用 |
| **数据预处理** | 组卷先 SQL 筛选再 AI 优化；分析先预聚合再送 LLM | 输入减少 70-80% |
| **Prompt 优化** | 结构化 JSON 输出 + 精简 few-shot + 正文截断 + 上下文窗口控制 | 减少 20-30% |

### 5.3 模型分级策略

```python
MODEL_TIERS = {
    'lite':     {'model': 'gpt-4o-mini', 'max_tokens': 1000, 'temperature': 0.3},
    'standard': {'model': 'gpt-4o-mini', 'max_tokens': 2000, 'temperature': 0.5},
    'complex':  {'model': 'gpt-4o',      'max_tokens': 4000, 'temperature': 0.7},
}

FUNCTION_MODEL_MAP = {
    'question_analyze':      'standard',  # 题目解析
    'exam_compose':          'standard',  # 智能组卷
    'ai_grade':              'complex',   # 主观题判卷（需强理解力）
    'exam_analyze':          'complex',   # 试卷分析（需综合推理）
    'review_recommend':      'lite',      # 复习推荐（模式化输出）
    'learning_profile':      'complex',   # 答题分析（需深度分析）
    'article_enhance':       'standard',  # 文章增强
    'tag_recommend':         'lite',      # 标签推荐
}
```

---

## 六、技术架构设计

### 6.1 分层架构

```
┌─────────────────────────────────────────┐
│  前端展示层                                │
│  Web 管理后台 (Vue3+Element Plus)         │
│  微信小程序 (原生 WXML/WXSS/JS)            │
├─────────────────────────────────────────┤
│  业务接口层 (adminapi/)                    │
│  views_ai.py (AI 接口入口)               │
│  views_data.py (数据 CRUD + 批量操作)      │
│  views_import.py (批量导入)               │
├─────────────────────────────────────────┤
│  AI 服务层 (新建 ai_services.py)           │
│  AIServiceBase (缓存/重试/脱敏/模型选择)    │
│  ├── QuestionAnalysisService (题目解析)    │
│  ├── ExamCompositionService (智能组卷)     │
│  ├── GradingService (智能判卷)            │
│  ├── ExamAnalysisService (试卷分析)        │
│  ├── ReviewRecommendService (复习推荐)     │
│  ├── LearningProfileService (答题分析)     │
│  └── ArticleEnhanceService (文章增强)      │
├─────────────────────────────────────────┤
│  基础设施层                                │
│  _call_llm() (已有) │ ai_config (已有)    │
│  AICacheManager (新建) │ AIJobManager (新建)│
│  PromptBuilder (新建) │ RateLimiter (已有)  │
├─────────────────────────────────────────┤
│  数据层: SQLite + Document 通用文档模型     │
└─────────────────────────────────────────┘
```

### 6.2 新增模块文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `backend/adminapi/ai_services.py` | 新建 | AI 服务层核心：基类 + 8 个业务服务类 |
| `backend/adminapi/ai_cache.py` | 新建 | 缓存管理器：content_hash、缓存读写、失效 |
| `backend/adminapi/ai_prompts.py` | 新建 | Prompt 模板库：各功能 system/user prompt 构建器 |
| `backend/adminapi/ai_jobs.py` | 新建 | 异步任务管理器：线程池 + 状态机 + 进度回调 |
| `backend/adminapi/views_ai.py` | 修改 | 扩展 AI 接口，新增 15+ 个视图函数 |
| `backend/adminapi/permissions.py` | 修改 | 新增 6 个 AI 权限点 |
| `backend/adminapi/urls.py` | 修改 | 注册新 AI 路由 |
| `backend/backend/settings.py` | 修改 | 新增 AI 功能级默认配置 |

### 6.3 新增 Collection

| Collection | 用途 |
|------------|------|
| `ai_learning_profile` | 用户学习画像（答题分析结果） |
| `ai_review_plans` | 每日复习推荐清单 |
| `ai_jobs` | 异步 AI 任务状态追踪 |

### 6.4 扩展字段

| 文档 | 字段 | 说明 |
|------|------|------|
| `questions.data` | `ai_analysis` | 题目 AI 解析结果 |
| `exam.data` | `ai_analysis` | 试卷 AI 分析结果 |
| `historys.data.items[n]` | `ai_grading` | 主观题 AI 评分结果 |
| `ai_config.data` | `feature_config` | 功能级 AI 配置 |

---

## 七、异步任务方案

### 7.1 方案选型

与现有 `ImportJob` 保持一致，使用 `threading.Thread` 守护线程，**不引入 Celery/Redis**。

### 7.2 各功能同步/异步选择

| 功能 | 模式 | 理由 |
|------|:---:|------|
| 单题 AI 解析 | 同步 | < 5 秒，用户可接受 |
| 批量题目解析（≥5 题） | 异步 | 10-60 秒 |
| AI 智能组卷 | 异步 | 10-20 秒 |
| 单题 AI 判卷 | 同步 | < 5 秒，需即时反馈 |
| 批量判卷 | 异步 | 5-10 道主观题逐题调用 |
| 试卷分析 | 异步 | 15-30 秒 |
| 答题分析 | 异步 | 10-20 秒 |
| 复习推荐 | 异步 | 5-10 秒 |
| 文章增强 | 同步 | 复用现有接口 |

### 7.3 前端轮询

| 端 | 间隔 | 最大次数 | 超时处理 |
|----|:---:|:---:|------|
| Web 管理后台 | 2 秒 | 150 次（5 分钟） | 提示"任务超时" |
| 小程序 | 3 秒 | 100 次（5 分钟） | 同上 |

---

## 八、权限点扩展与 API 路由设计

### 8.1 新增权限点（6 个）

| 权限码 | 名称 | 分组 |
|--------|------|------|
| `ai.analyze` | AI 题目解析 | AI 设置 |
| `ai.compose` | AI 智能组卷 | AI 设置 |
| `ai.grade` | AI 智能判卷 | AI 设置 |
| `ai.report` | AI 分析报告 | AI 设置 |
| `ai.recommend` | AI 推荐管理 | AI 设置 |
| `ai.job.view` | AI 任务查看 | AI 设置 |

### 8.2 管理端 AI 接口（`/api/admin/ai/`）

| 方法 | 路径 | 权限 | 同步/异步 | 说明 |
|------|------|------|:---:|------|
| POST | `/ai/questions/<id>/analyze/` | `ai.analyze` | 同步 | 单题 AI 解析 |
| POST | `/ai/questions/analyze-batch/` | `ai.analyze` | 异步 | 批量题目解析 |
| POST | `/ai/compose/` | `ai.compose` | 异步 | AI 智能组卷 |
| GET | `/ai/compose/<job_id>/` | `ai.compose` | — | 组卷状态查询 |
| POST | `/ai/compose/<job_id>/confirm/` | `ai.compose` | 同步 | 确认组卷结果 |
| POST | `/ai/questions/<id>/ai-grade/` | `ai.grade` | 同步 | 单题 AI 判卷 |
| POST | `/ai/grade-batch/` | `ai.grade` | 异步 | 批量判卷 |
| POST | `/ai/exams/<examid>/analyze/` | `ai.report` | 异步 | AI 试卷分析 |
| GET | `/ai/exams/<examid>/analysis/` | `ai.report` | 同步 | 获取分析结果 |
| GET | `/ai/jobs/` | `ai.job.view` | 同步 | AI 任务列表 |
| GET | `/ai/jobs/<job_id>/` | `ai.job.view` | 同步 | 查询任务状态 |
| POST | `/ai/jobs/<job_id>/cancel/` | `ai.job.view` | 同步 | 取消任务 |

### 8.3 小程序端 AI 接口（`/api/ai/`）

| 方法 | 路径 | 鉴权 | 同步/异步 | 说明 |
|------|------|------|:---:|------|
| POST | `/api/ai/assist/` | X-Openid | 同步 | AI 辅助撰写（已有） |
| POST | `/api/ai/review-plan/` | X-Openid | 异步 | 生成今日复习推荐 |
| GET | `/api/ai/review-plan/` | X-Openid | 同步 | 获取今日复习推荐 |
| POST | `/api/ai/learning-profile/` | X-Openid | 异步 | 生成答题分析 |
| GET | `/api/ai/learning-profile/` | X-Openid | 同步 | 获取答题分析结果 |
| GET | `/api/ai/jobs/<job_id>/` | X-Openid | 同步 | 查询异步任务状态 |

---

## 九、数据结构设计

### 9.1 题目解析结果：`questions.data.ai_analysis`

```json
{
  "version": 1,
  "content_hash": "a1b2c3d4e5f6",
  "model": "gpt-4o-mini",
  "analyzed_at": "2026-09-20T10:30:00Z",
  "knowledge_points": [
    {"name": "二叉树遍历", "confidence": 0.95},
    {"name": "递归", "confidence": 0.88}
  ],
  "difficulty": "medium",
  "difficulty_score": 6,
  "qtype_detected": "single",
  "answer_analysis_md": "本题考察二叉树前序遍历...",
  "suggested_tags": [
    {"category": "knowledge", "name": "数据结构", "tag_id": 5},
    {"category": "difficulty", "name": "中等", "tag_id": 2}
  ],
  "key_concepts": ["二叉树", "前序遍历"],
  "common_mistakes": "常见错误：混淆前序和中序遍历的顺序"
}
```

### 9.2 判卷结果：`historys.items[n].ai_grading`

```json
{
  "score": 8,
  "max_score": 10,
  "feedback_md": "答题要点覆盖了前序遍历的定义...",
  "confidence": 0.85,
  "model": "gpt-4o",
  "graded_at": "2026-09-20T10:35:00Z",
  "content_hash": "b2c3d4e5f6a1",
  "human_review": {
    "reviewed": false,
    "adjusted_score": null,
    "reviewer": null,
    "reviewed_at": null
  }
}
```

### 9.3 学习画像：`ai_learning_profile`

```json
{
  "_openid": "oDWYj0WCCR-i5kok",
  "version": 1,
  "content_hash": "c3d4e5f6a1b2",
  "record_count": 48,
  "weak_points": [
    {"knowledge_point": "二叉树", "accuracy": 0.35, "total_attempts": 12, "recommendation": "建议复习二叉树遍历算法"}
  ],
  "error_patterns": [
    {"pattern": "概念混淆", "frequency": 8, "suggestion": "建议制作对比记忆卡片"}
  ],
  "ability_radar": {
    "labels": ["基础知识", "应用能力", "综合分析", "计算能力", "记忆理解"],
    "values": [0.85, 0.65, 0.45, 0.70, 0.80]
  },
  "recommendations": [
    {"type": "weak_point_drill", "target": "二叉树", "question_count": 10, "priority": "high"}
  ],
  "trend": {
    "accuracy_trend": [0.55, 0.62, 0.68, 0.72, 0.75],
    "activity_trend": [3, 5, 4, 6, 8]
  }
}
```

### 9.4 复习推荐：`ai_review_plans`

```json
{
  "_openid": "oDWYj0WCCR-i5kok",
  "plan_date": "2026-09-20",
  "items": [
    {
      "question_id": "q-001",
      "title": "二叉树前序遍历",
      "reason": "艾宾浩斯曲线：上次错误距今3天，进入第二复习周期",
      "priority": 1,
      "review_cycle": 2,
      "status": "pending"
    }
  ],
  "summary": {"total_items": 8, "estimated_time_min": 20, "weak_focus": "二叉树、进程调度"}
}
```

### 9.5 异步任务：`ai_jobs`

```json
{
  "job_type": "analyze_batch",
  "status": "running",
  "config": {"question_ids": ["q-001", "q-002"]},
  "result": null,
  "progress": 45,
  "progress_text": "已解析 5/10 题",
  "error": null,
  "openid": null,
  "created_at": "2026-09-20T10:00:00Z"
}
```

---

## 十、实现优先级与任务分解

### 10.1 P0 实现顺序

```
T01 基础设施层 (2天) → T02 题目解析+组卷 (3天)
                     → T03 智能判卷 (2天)    ← 可并行
```

### 10.2 任务分解（5 个任务）

| Task | 名称 | 优先级 | 文件数 | 依赖 | 预计工期 |
|------|------|:---:|:---:|------|:---:|
| T01 | AI 基础设施层 | P0 | 8 | 无 | 2 天 |
| T02 | 题目解析 + 智能组卷 | P0 | 5 | T01 | 3 天 |
| T03 | 智能判卷 | P0 | 5 | T01 | 2 天 |
| T04 | P1 分析+推荐+文章 | P1 | 5 | T01 | 4 天 |
| T05 | 前端 AI 功能页面 | P0+P1 | 14 | T01-T04 | 5 天 |

**并行可行性**：T02、T03、T04 在 T01 完成后可完全并行开发。

### 10.3 T01 基础设施层详细内容

1. **ai_services.py**：`AIServiceBase` 基类（模型选择、LLM 调用三级降级、脱敏、缓存读写、prompt 构建、响应解析）
2. **ai_cache.py**：`AICacheManager`（SHA-256 hash、缓存读写、批量失效、全局失效）
3. **ai_jobs.py**：`AIJobManager`（创建/启动/更新/查询/取消/清理超时任务）
4. **ai_prompts.py**：`PromptBuilder`（8 个功能 prompt 构建器、JSON 解析器）
5. **permissions.py**：新增 6 个权限点 + 角色更新
6. **views_ai.py**：扩展配置接口 + 任务管理接口
7. **urls.py**：注册新路由
8. **settings.py**：AI 功能级默认配置

---

## 十一、潜在风险与注意事项

### 11.1 风险矩阵

| 风险 | 等级 | 影响 | 缓解措施 |
|------|:---:|------|---------|
| LLM 调用超时/不稳定 | 🔴 高 | 用户等待过长 | 60s 超时 + 异步模式 + 重试 1 次 + 降级返回缓存/默认 |
| 学生数据隐私泄露 | 🔴 高 | PII 发送到外部 | 脱敏处理（移除 _openid/昵称/手机号）+ 仅发送学习数据 |
| AI 生成内容质量不稳定 | 🟡 中 | 错误知识点/不合理评分 | 结构化 prompt + 人工复核（判卷 hybrid）+ 置信度预警 |
| Token 成本超支 | 🟡 中 | 意外高额账单 | 日 Token 预算上限 + 缓存优先 + 分级模型 + 限流 |
| 并发 LLM 调用过载 | 🟡 中 | 线程过多/API 限流 | 功能级限流 30次/分钟 + 批量任务串行 + 线程数上限 |
| 缓存数据不一致 | 🟡 中 | 显示旧分析结果 | content_hash 自动失效 + 编辑时主动清除 + 手动重新分析 |
| SQLite 并发写入冲突 | 🟢 低 | 异步任务写入冲突 | Django ORM 串行化 + 独立 DB 连接 + 重试 |
| 异步任务进程崩溃 | 🟢 低 | 任务卡在 running | 超时检测（>10min 标记 failed）+ 启动时清理残留 |

### 11.2 LLM 三级降级策略

```
正常调用 _call_llm() 
  → 失败 → 重试 1 次（间隔 2 秒）
    → 失败 → 返回缓存（允许过期缓存）
      → 无缓存 → 返回降级结果（如判卷降级为关键词匹配）
        → 无法降级 → 抛出异常
```

### 11.3 数据脱敏规则

```python
PII_FIELDS = ['_openid', 'nickName', 'avatarUrl', 'phone', 'email', 'city', 'userInfo']

def sanitize_for_llm(data: dict) -> dict:
    """移除 PII 字段，仅保留学习相关数据。"""
    return {k: v for k, v in data.items() if k not in PII_FIELDS}
```

### 11.4 AI 生成内容标注

| 场景 | 标注方式 |
|------|---------|
| 题目解析 | 标注"AI 解析"，记录 model + analyzed_at |
| 判卷评语 | 评语前缀 "[AI 评语]"，人工复核后改 "[人工复核]" |
| 试卷分析 | 报告标题含"AI 生成"，底部标注模型和时间 |
| 复习推荐 | 推荐理由标注 "[艾宾浩斯复习周期]" 或 "[AI 智能推荐]" |
| 文章辅助 | 标注"AI 生成内容，请审核" |

---

## 十二、待确认问题与架构建议

| 问题 | 架构建议 |
|------|---------|
| Q1: LLM 服务商？ | 兼容任何 OpenAI 格式 API，建议默认 gpt-4o-mini，判卷/分析用 gpt-4o |
| Q2: Token 预算？ | 预估 P0+P1 月成本 <$1，建议月预算 $10（含余量） |
| Q3: 向量数据库？ | P0/P1 不引入；P2 RAG 可考虑 sqlite-vss 或关键词检索 |
| Q4: 知识点映射？ | 映射到现有 Tag 体系（category=knowledge），不新建体系 |
| Q5: 判卷 hybrid？ | AI 初判 + 人工复核，confidence<0.7 自动标记需复核 |
| Q6: 组卷查重？ | 按 examid + 归一化题干去重（复用 ImportJob 逻辑） |
| Q7: 复习推荐模式？ | 艾宾浩斯算法为主 + AI 优化为辅（算法保证科学性，AI 增强个性化） |
| Q8: AI 内容标注？ | 统一标注 [AI 生成]，记录 model + 时间 |
| Q9: 小程序配额？ | 复习推荐 1次/天，答题分析 1次/7天，文章 10次/60s。暂不设付费墙 |
| Q10: 数据脱敏？ | 送 LLM 前移除 _openid/昵称等 PII，仅保留学习数据 |
| Q11: 任务队列？ | threading.Thread + ai_jobs collection，不引入 Celery |
| Q12: 失败降级？ | 三级：重试 → 缓存 → 降级结果 |

---

## 附录：交付文件清单

| # | 文件路径 | 说明 |
|---|---------|------|
| 1 | `docs/AI能力规划方案.md` | **本文件** — 完整规划方案（汇总 PRD + 技术设计） |
| 2 | `docs/AI能力技术架构设计.md` | 架构师技术设计详案（1580 行，含类图/时序图/任务分解） |
| 3 | `docs/ai-class-diagram.mermaid` | 类图（Mermaid classDiagram） |
| 4 | `docs/ai-sequence-diagram.mermaid` | 时序图（4 个关键流程） |

---

> **文档结束**。以上为考试宝 AI 能力规划方案 v1.0，待确认 Q1-Q12 后可进入实施阶段。
