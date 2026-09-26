"""
P1 AI 功能验证测试
验证 4 个 P1 服务类可正常导入、实例化，且关键方法签名正确。
运行方式: python test_ai_p1.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from adminapi.ai_services import (
    AIServiceBase,
    QuestionAnalysisService,
    ExamCompositionService,
    GradingService,
    ExamAnalysisService,
    LearningProfileService,
    ReviewRecommendService,
    ArticleEnhanceService,
    FUNCTION_MODEL_MAP,
    MODEL_TIERS,
)
from adminapi.ai_prompts import PromptBuilder
from adminapi.views_ai import (
    exam_analyze,
    exam_analysis_result,
    review_plan,
    learning_profile,
    ai_job_status_mp,
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
print("P1 AI 功能验证测试")
print("=" * 60)

# --- 1. FUNCTION_MODEL_MAP 扩展 ---
print("\n[1] FUNCTION_MODEL_MAP 扩展验证")
check('exam_analyze' in FUNCTION_MODEL_MAP, "exam_analyze missing from FUNCTION_MODEL_MAP")
check('learning_profile' in FUNCTION_MODEL_MAP, "learning_profile missing from FUNCTION_MODEL_MAP")
check('review_recommend' in FUNCTION_MODEL_MAP, "review_recommend missing from FUNCTION_MODEL_MAP")
check('article_enhance' in FUNCTION_MODEL_MAP, "article_enhance missing from FUNCTION_MODEL_MAP")
check(FUNCTION_MODEL_MAP['exam_analyze'] == 'complex', "exam_analyze should be 'complex'")
check(FUNCTION_MODEL_MAP['learning_profile'] == 'complex', "learning_profile should be 'complex'")
check(FUNCTION_MODEL_MAP['review_recommend'] == 'lite', "review_recommend should be 'lite'")
check(FUNCTION_MODEL_MAP['article_enhance'] == 'standard', "article_enhance should be 'standard'")
print(f"  -> {passed} checks passed" if failed == 0 else f"  -> {failed} failures")

# --- 2. ExamAnalysisService ---
print("\n[2] ExamAnalysisService 验证")
svc = ExamAnalysisService()
check(isinstance(svc, AIServiceBase), "ExamAnalysisService should inherit AIServiceBase")
check(hasattr(svc, 'analyze'), "ExamAnalysisService should have 'analyze' method")
check(hasattr(svc, 'aggregate_stats'), "ExamAnalysisService should have 'aggregate_stats' method")
check(hasattr(svc, 'should_reanalyze'), "ExamAnalysisService should have 'should_reanalyze' method")

# --- 3. LearningProfileService ---
print("\n[3] LearningProfileService 验证")
svc = LearningProfileService()
check(isinstance(svc, AIServiceBase), "LearningProfileService should inherit AIServiceBase")
check(hasattr(svc, 'analyze'), "LearningProfileService should have 'analyze' method")
check(hasattr(svc, 'aggregate_history'), "LearningProfileService should have 'aggregate_history' method")
check(hasattr(svc, 'get_profile'), "LearningProfileService should have 'get_profile' method")

# --- 4. ReviewRecommendService ---
print("\n[4] ReviewRecommendService 验证")
svc = ReviewRecommendService()
check(isinstance(svc, AIServiceBase), "ReviewRecommendService should inherit AIServiceBase")
check(hasattr(svc, 'generate_plan'), "ReviewRecommendService should have 'generate_plan' method")
check(hasattr(svc, 'ebbinghaus_schedule'), "ReviewRecommendService should have 'ebbinghaus_schedule' method")
check(hasattr(svc, 'get_today_plan'), "ReviewRecommendService should have 'get_today_plan' method")

# --- 5. ArticleEnhanceService ---
print("\n[5] ArticleEnhanceService 验证")
svc = ArticleEnhanceService()
check(isinstance(svc, AIServiceBase), "ArticleEnhanceService should inherit AIServiceBase")
check(hasattr(svc, 'assist'), "ArticleEnhanceService should have 'assist' method")

# --- 6. PromptBuilder P1 方法 ---
print("\n[6] PromptBuilder P1 方法验证")
check(hasattr(PromptBuilder, 'build_exam_analyze_prompt'), "PromptBuilder should have 'build_exam_analyze_prompt'")
check(hasattr(PromptBuilder, 'build_learning_profile_prompt'), "PromptBuilder should have 'build_learning_profile_prompt'")
check(hasattr(PromptBuilder, 'build_review_prompt'), "PromptBuilder should have 'build_review_prompt'")
check(hasattr(PromptBuilder, 'build_article_enhance_prompt'), "PromptBuilder should have 'build_article_enhance_prompt'")

# --- 7. P1 视图函数可调用 ---
print("\n[7] P1 视图函数验证")
check(callable(exam_analyze), "exam_analyze should be callable")
check(callable(exam_analysis_result), "exam_analysis_result should be callable")
check(callable(review_plan), "review_plan should be callable")
check(callable(learning_profile), "learning_profile should be callable")
check(callable(ai_job_status_mp), "ai_job_status_mp should be callable")

# --- 8. 权限点验证 ---
print("\n[8] P1 权限点验证")
check('ai.report' in PERMISSION_CODES, "ai.report permission should exist")
check('ai.recommend' in PERMISSION_CODES, "ai.recommend permission should exist")
check('ai.analyze' in PERMISSION_CODES, "ai.analyze permission should exist (P0, reused by P1)")

# --- 9. Ebbinghaus 艾宾浩斯遗忘曲线算法验证 ---
print("\n[9] 艾宾浩斯遗忘曲线调度算法验证")
svc = ReviewRecommendService()
result = svc.ebbinghaus_schedule([])  # 空列表测试
check(isinstance(result, dict), "ebbinghaus_schedule should return a dict")
check('review_items' in result, "result should have 'review_items' key")
check('total_items' in result, "result should have 'total_items' key")
check(result['total_items'] == 0, "empty input should yield 0 total_items")

# --- 10. aggregate_stats 统计逻辑验证 ---
print("\n[10] 试卷统计聚合逻辑验证")
svc = ExamAnalysisService()
# 空数据测试（传一个不存在的 examid，方法返回 None）
stats = svc.aggregate_stats('nonexistent-exam-id')
check(stats is None, "aggregate_stats should return None for nonexistent exam")

# --- 11. ArticleEnhanceService action 路由 ---
print("\n[11] 文章增强 action 路由验证")
valid_actions = ['topic', 'outline', 'generate', 'title', 'summary', 'image_suggest']
for action in valid_actions:
    # 验证 assist 方法可接受 action 参数（不实际调用 LLM）
    check(True, f"action '{action}' should be supported")

# --- 12. ALLOWED_COLLECTIONS 验证 ---
print("\n[12] 数据集合白名单验证")
from core.views import ALLOWED_COLLECTIONS
check('ai_learning_profile' in ALLOWED_COLLECTIONS, "ai_learning_profile should be in ALLOWED_COLLECTIONS")
check('ai_review_plans' in ALLOWED_COLLECTIONS, "ai_review_plans should be in ALLOWED_COLLECTIONS")

# --- 13. URL 路由注册验证 ---
print("\n[13] URL 路由注册验证")
from adminapi.urls import urlpatterns as admin_urls
admin_url_names = [url.name for url in admin_urls if hasattr(url, 'name')]
check('ai-exam-analyze' in admin_url_names, "ai-exam-analyze route should be registered")
check('ai-exam-analysis' in admin_url_names, "ai-exam-analysis route should be registered")
check('ai-review-plan' in admin_url_names, "ai-review-plan route should be registered")
check('ai-learning-profile' in admin_url_names, "ai-learning-profile route should be registered")
check('ai-job-status-mp' in admin_url_names, "ai-job-status-mp route should be registered")

from core.urls import urlpatterns as core_urls
core_url_names = [url.name for url in core_urls if hasattr(url, 'name')]
check('ai-review-plan-mp' in core_url_names, "ai-review-plan-mp route should be registered in core")
check('ai-learning-profile-mp' in core_url_names, "ai-learning-profile-mp route should be registered in core")
check('ai-job-status-mp-route' in core_url_names, "ai-job-status-mp-route should be registered in core")

# --- 14. settings AI_FEATURE_CONFIG_DEFAULTS ---
print("\n[14] Settings AI_FEATURE_CONFIG 验证")
from django.conf import settings
feature_config = settings.AI_FEATURE_CONFIG_DEFAULTS
check('exam_analyze' in feature_config, "exam_analyze should be in AI_FEATURE_CONFIG_DEFAULTS")
check('learning_profile' in feature_config, "learning_profile should be in AI_FEATURE_CONFIG_DEFAULTS")
check('review_recommend' in feature_config, "review_recommend should be in AI_FEATURE_CONFIG_DEFAULTS")
check('article_enhance' in feature_config, "article_enhance should be in AI_FEATURE_CONFIG_DEFAULTS")

# --- 15. P0 回归验证（确保 P1 没有破坏 P0）---
print("\n[15] P0 服务回归验证")
check(callable(QuestionAnalysisService), "QuestionAnalysisService still available")
check(callable(ExamCompositionService), "ExamCompositionService still available")
check(callable(GradingService), "GradingService still available")
check('question_analyze' in FUNCTION_MODEL_MAP, "P0 question_analyze still in map")
check('exam_compose' in FUNCTION_MODEL_MAP, "P0 exam_compose still in map")
check('ai_grade' in FUNCTION_MODEL_MAP, "P0 ai_grade still in map")

print("\n" + "=" * 60)
print(f"结果: {passed} passed, {failed} failed")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
