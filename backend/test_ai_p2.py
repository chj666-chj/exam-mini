"""
P2 AI 功能验证测试
验证 5 个 P2 服务类可正常导入、实例化，关键方法签名正确，
以及路由 / 配置 / 集合白名单 / Prompt 均已正确注册。
运行方式: python test_ai_p2.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from adminapi.ai_services import (
    AIServiceBase,
    KnowledgeRAGService,
    AutoTagService,
    ExcelValidateService,
    LearningReportService,
    CustomerService,
    FUNCTION_MODEL_MAP,
    MODEL_TIERS,
)
from adminapi.ai_prompts import PromptBuilder
from adminapi.views_ai import (
    kb_rebuild,
    kb_stats,
    question_suggest_tags,
    question_auto_tag_batch,
    question_apply_tags,
    excel_validate,
    kb_ask,
    learning_report,
    cs_chat,
)
from adminapi.permissions import PERMISSION_CODES

passed = 0
failed = 0


def check(condition, msg):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {msg}")


print("=" * 60)
print("P2 AI 功能验证测试")
print("=" * 60)

# --- 1. FUNCTION_MODEL_MAP 扩展 ---
print("\n[1] FUNCTION_MODEL_MAP 扩展验证")
check('kb_qa' in FUNCTION_MODEL_MAP, "kb_qa missing from FUNCTION_MODEL_MAP")
check('auto_tag' in FUNCTION_MODEL_MAP, "auto_tag missing from FUNCTION_MODEL_MAP")
check('excel_validate' in FUNCTION_MODEL_MAP, "excel_validate missing from FUNCTION_MODEL_MAP")
check('learning_report' in FUNCTION_MODEL_MAP, "learning_report missing from FUNCTION_MODEL_MAP")
check('cs_chat' in FUNCTION_MODEL_MAP, "cs_chat missing from FUNCTION_MODEL_MAP")
check(FUNCTION_MODEL_MAP['kb_qa'] == 'standard', "kb_qa should be 'standard'")
check(FUNCTION_MODEL_MAP['auto_tag'] == 'standard', "auto_tag should be 'standard'")
check(FUNCTION_MODEL_MAP['excel_validate'] == 'complex', "excel_validate should be 'complex'")
check(FUNCTION_MODEL_MAP['learning_report'] == 'complex', "learning_report should be 'complex'")
check(FUNCTION_MODEL_MAP['cs_chat'] == 'standard', "cs_chat should be 'standard'")
check(FUNCTION_MODEL_MAP['excel_validate'] in MODEL_TIERS, "excel_validate tier should exist in MODEL_TIERS")

# --- 2. KnowledgeRAGService ---
print("\n[2] KnowledgeRAGService 验证")
svc = KnowledgeRAGService()
check(isinstance(svc, AIServiceBase), "KnowledgeRAGService should inherit AIServiceBase")
check(hasattr(svc, 'build_corpus'), "KnowledgeRAGService should have 'build_corpus'")
check(hasattr(svc, 'tokenize'), "KnowledgeRAGService should have 'tokenize'")
check(hasattr(svc, 'retrieve'), "KnowledgeRAGService should have 'retrieve'")
check(hasattr(svc, 'ask'), "KnowledgeRAGService should have 'ask'")
check(hasattr(svc, 'rebuild_index'), "KnowledgeRAGService should have 'rebuild_index'")
check(hasattr(svc, 'get_stats'), "KnowledgeRAGService should have 'get_stats'")
check(KnowledgeRAGService.COLLECTION == 'ai_kb_answers', "COLLECTION should be 'ai_kb_answers'")

# --- 3. AutoTagService ---
print("\n[3] AutoTagService 验证")
svc = AutoTagService()
check(isinstance(svc, AIServiceBase), "AutoTagService should inherit AIServiceBase")
check(hasattr(svc, 'suggest_tags'), "AutoTagService should have 'suggest_tags'")
check(hasattr(svc, 'suggest_batch'), "AutoTagService should have 'suggest_batch'")
check(hasattr(svc, 'apply_tags'), "AutoTagService should have 'apply_tags'")

# --- 4. ExcelValidateService ---
print("\n[4] ExcelValidateService 验证")
svc = ExcelValidateService()
check(isinstance(svc, AIServiceBase), "ExcelValidateService should inherit AIServiceBase")
check(hasattr(svc, 'validate_rows'), "ExcelValidateService should have 'validate_rows'")
check(ExcelValidateService.BATCH_SIZE == 20, "BATCH_SIZE should be 20")

# --- 5. LearningReportService ---
print("\n[5] LearningReportService 验证")
svc = LearningReportService()
check(isinstance(svc, AIServiceBase), "LearningReportService should inherit AIServiceBase")
check(hasattr(svc, '_period_range'), "LearningReportService should have '_period_range'")
check(hasattr(svc, 'aggregate'), "LearningReportService should have 'aggregate'")
check(hasattr(svc, 'generate'), "LearningReportService should have 'generate'")
check(hasattr(svc, 'get_report'), "LearningReportService should have 'get_report'")
check(LearningReportService.COLLECTION == 'ai_reports', "COLLECTION should be 'ai_reports'")
check(LearningReportService.TYPES == ('weekly', 'monthly', 'pre_exam'), "TYPES mismatch")

# --- 6. CustomerService ---
print("\n[6] CustomerService 验证")
svc = CustomerService()
check(isinstance(svc, AIServiceBase), "CustomerService should inherit AIServiceBase")
check(hasattr(svc, '_load_faq'), "CustomerService should have '_load_faq'")
check(hasattr(svc, 'chat'), "CustomerService should have 'chat'")

# --- 7. PromptBuilder P2 方法 ---
print("\n[7] PromptBuilder P2 方法验证")
check(hasattr(PromptBuilder, 'build_kb_qa_prompt'), "PromptBuilder should have 'build_kb_qa_prompt'")
check(hasattr(PromptBuilder, 'build_auto_tag_prompt'), "PromptBuilder should have 'build_auto_tag_prompt'")
check(hasattr(PromptBuilder, 'build_excel_validate_prompt'), "PromptBuilder should have 'build_excel_validate_prompt'")
check(hasattr(PromptBuilder, 'build_learning_report_prompt'), "PromptBuilder should have 'build_learning_report_prompt'")
check(hasattr(PromptBuilder, 'build_cs_chat_prompt'), "PromptBuilder should have 'build_cs_chat_prompt'")
check(PromptBuilder.build_system_prompt('kb_qa') != PromptBuilder.build_system_prompt('__none__'),
      "kb_qa system prompt should be registered")
check(PromptBuilder.build_system_prompt('cs_chat') != PromptBuilder.build_system_prompt('__none__'),
      "cs_chat system prompt should be registered")

# --- 8. P2 视图函数可调用 ---
print("\n[8] P2 视图函数验证")
check(callable(kb_rebuild), "kb_rebuild should be callable")
check(callable(kb_stats), "kb_stats should be callable")
check(callable(question_suggest_tags), "question_suggest_tags should be callable")
check(callable(question_auto_tag_batch), "question_auto_tag_batch should be callable")
check(callable(question_apply_tags), "question_apply_tags should be callable")
check(callable(excel_validate), "excel_validate should be callable")
check(callable(kb_ask), "kb_ask should be callable")
check(callable(learning_report), "learning_report should be callable")
check(callable(cs_chat), "cs_chat should be callable")

# --- 9. 权限点验证（复用，不新增）---
print("\n[9] P2 权限点（复用现有）验证")
check('ai.config' in PERMISSION_CODES, "ai.config should exist")
check('ai.analyze' in PERMISSION_CODES, "ai.analyze should exist")
check('question.import' in PERMISSION_CODES, "question.import should exist")
check('ai.report' in PERMISSION_CODES, "ai.report should exist")
check('ai.recommend' in PERMISSION_CODES, "ai.recommend should exist")

# --- 10. KnowledgeRAGService 纯函数验证 ---
print("\n[10] KnowledgeRAGService 纯函数验证")
tokens = KnowledgeRAGService.tokenize('请讲解一下二次函数的图像')
check(isinstance(tokens, list), "tokenize should return a list")
check(len(tokens) > 0, "tokenize should return non-empty tokens for Chinese text")
tokens_en = KnowledgeRAGService.tokenize('Binary Search Algorithm 2024')
check('binary' in tokens_en, "tokenize should lowercase english words")
check('2024' in tokens_en, "tokenize should keep numbers")

retrieved = KnowledgeRAGService.retrieve('一个不可能命中的问题 zzzqqq')
check(isinstance(retrieved, list), "retrieve should return a list")
check(retrieved == [], "retrieve should return [] when no corpus matches")

corpus = KnowledgeRAGService.build_corpus()
check(isinstance(corpus, list), "build_corpus should return a list")

stats = KnowledgeRAGService.get_stats()
check(isinstance(stats, dict), "get_stats should return a dict")
check('corpus_size' in stats, "get_stats should have 'corpus_size'")
check('cache_count' in stats, "get_stats should have 'cache_count'")

# --- 11. LearningReportService._period_range 验证 ---
print("\n[11] 学习报告周期计算验证")
for rtype in ('weekly', 'monthly', 'pre_exam'):
    rng = LearningReportService._period_range(rtype)
    check(isinstance(rng, tuple) and len(rng) == 3, f"{rtype} _period_range should return a 3-tuple")
    period_key, start_date, end_date = rng
    check(isinstance(period_key, str) and period_key, f"{rtype} period_key should be a non-empty str")
    check(isinstance(start_date, str) and len(start_date) == 10, f"{rtype} start_date should be YYYY-MM-DD")
    check(isinstance(end_date, str) and len(end_date) == 10, f"{rtype} end_date should be YYYY-MM-DD")
    check(start_date <= end_date, f"{rtype} start_date should be <= end_date")

weekly = LearningReportService._period_range('weekly')
check(weekly[0].count('-') == 1, "weekly period_key should be 'YYYY-WW'")
pre = LearningReportService._period_range('pre_exam')
check(pre[0].startswith('pre-'), "pre_exam period_key should start with 'pre-'")

# --- 12. ExcelValidateService 降级返回结构 ---
print("\n[12] ExcelValidateService 降级结构验证")
result = ExcelValidateService.validate_rows([{'title': '示例题目', 'answer': 'A'}], 'single')
check(isinstance(result, dict), "validate_rows should return a dict (even when LLM unavailable)")
for key in ('total', 'valid_count', 'error_count', 'errors', 'corrections', 'column_mapping'):
    check(key in result, f"validate_rows result should have '{key}'")
check(result['total'] == 1, "total should equal input row count")
check(isinstance(result['errors'], list), "errors should be a list")
check(isinstance(result['corrections'], list), "corrections should be a list")
check(isinstance(result['column_mapping'], dict), "column_mapping should be a dict")

empty_result = ExcelValidateService.validate_rows([], 'single')
check(empty_result['total'] == 0, "empty input should yield total=0")
check(empty_result['valid_count'] == 0, "empty input should yield valid_count=0")

# --- 13. ALLOWED_COLLECTIONS / PRIVATE_COLLECTIONS 验证 ---
print("\n[13] 数据集合白名单验证")
from core.views import ALLOWED_COLLECTIONS, PRIVATE_COLLECTIONS
check('ai_kb_answers' in ALLOWED_COLLECTIONS, "ai_kb_answers should be in ALLOWED_COLLECTIONS")
check('ai_reports' in ALLOWED_COLLECTIONS, "ai_reports should be in ALLOWED_COLLECTIONS")
check('ai_reports' in PRIVATE_COLLECTIONS, "ai_reports should be in PRIVATE_COLLECTIONS")

# --- 14. URL 路由注册验证 ---
print("\n[14] URL 路由注册验证")
from adminapi.urls import urlpatterns as admin_urls
admin_url_names = [url.name for url in admin_urls if hasattr(url, 'name')]
check('ai-kb-rebuild' in admin_url_names, "ai-kb-rebuild route should be registered")
check('ai-kb-stats' in admin_url_names, "ai-kb-stats route should be registered")
check('ai-question-suggest-tags' in admin_url_names, "ai-question-suggest-tags route should be registered")
check('ai-question-apply-tags' in admin_url_names, "ai-question-apply-tags route should be registered")
check('ai-question-auto-tag' in admin_url_names, "ai-question-auto-tag route should be registered")
check('ai-excel-validate' in admin_url_names, "ai-excel-validate route should be registered")

from core.urls import urlpatterns as core_urls
core_url_names = [url.name for url in core_urls if hasattr(url, 'name')]
check('ai-kb-ask-mp' in core_url_names, "ai-kb-ask-mp route should be registered in core")
check('ai-report-mp' in core_url_names, "ai-report-mp route should be registered in core")
check('ai-cs-chat-mp' in core_url_names, "ai-cs-chat-mp route should be registered in core")

# --- 15. settings AI_FEATURE_CONFIG_DEFAULTS ---
print("\n[15] Settings AI_FEATURE_CONFIG 验证")
from django.conf import settings
feature_config = settings.AI_FEATURE_CONFIG_DEFAULTS
check('kb_qa' in feature_config, "kb_qa should be in AI_FEATURE_CONFIG_DEFAULTS")
check('auto_tag' in feature_config, "auto_tag should be in AI_FEATURE_CONFIG_DEFAULTS")
check('excel_validate' in feature_config, "excel_validate should be in AI_FEATURE_CONFIG_DEFAULTS")
check('learning_report' in feature_config, "learning_report should be in AI_FEATURE_CONFIG_DEFAULTS")
check('cs_chat' in feature_config, "cs_chat should be in AI_FEATURE_CONFIG_DEFAULTS")
for fn in ('kb_qa', 'auto_tag', 'excel_validate', 'learning_report', 'cs_chat'):
    cfg = feature_config.get(fn, {})
    check('enabled' in cfg and 'temperature' in cfg and 'max_tokens' in cfg,
          f"{fn} feature config should have enabled/temperature/max_tokens")

# --- 16. P0/P1 回归验证（确保 P2 没有破坏既有服务）---
print("\n[16] P0/P1 服务回归验证")
from adminapi.ai_services import (
    QuestionAnalysisService, ExamCompositionService, GradingService,
    ExamAnalysisService, LearningProfileService, ReviewRecommendService,
    ArticleEnhanceService,
)
check(callable(QuestionAnalysisService), "QuestionAnalysisService still available")
check(callable(ExamCompositionService), "ExamCompositionService still available")
check(callable(GradingService), "GradingService still available")
check(callable(ExamAnalysisService), "ExamAnalysisService still available")
check(callable(LearningProfileService), "LearningProfileService still available")
check(callable(ReviewRecommendService), "ReviewRecommendService still available")
check(callable(ArticleEnhanceService), "ArticleEnhanceService still available")
check('question_analyze' in FUNCTION_MODEL_MAP, "P0 question_analyze still in map")
check('exam_analyze' in FUNCTION_MODEL_MAP, "P1 exam_analyze still in map")
check('article_enhance' in FUNCTION_MODEL_MAP, "P1 article_enhance still in map")

print("\n" + "=" * 60)
print(f"结果: {passed} passed, {failed} failed")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
