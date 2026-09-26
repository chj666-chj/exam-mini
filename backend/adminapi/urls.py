"""管理端 REST 接口路由（挂载在 /api/admin/ 下）。"""
from django.urls import path, re_path

from . import views_admin, views_auth, views_dashboard, views_data, views_import, views_profile, views_tags, views_ai, views_ai_analytics


def question_tags_dispatch(request, doc_id):
    """GET 查看绑定 / PUT 全量替换绑定"""
    if request.method == 'GET':
        return views_tags.question_tags(request, doc_id)
    return views_tags.question_tags_bind(request, doc_id)

urlpatterns = [
    # ---- 认证 ----
    path('auth/login/', views_auth.login, name='admin-login'),
    path('auth/logout/', views_auth.logout, name='admin-logout'),
    path('auth/me/', views_auth.profile, name='admin-me'),
    path('auth/profile/', views_auth.profile, name='admin-profile'),
    path('auth/password/', views_auth.change_password, name='admin-password'),
    path('auth/permissions/', views_auth.permission_tree, name='admin-permissions'),

    # ---- 数据看板 ----
    path('dashboard/overview/', views_dashboard.overview, name='admin-overview'),
    path('dashboard/trend/', views_dashboard.trend, name='admin-trend'),
    path('dashboard/ranking/', views_dashboard.ranking, name='admin-ranking'),
    path('dashboard/logs/', views_dashboard.operation_logs, name='admin-logs'),

    # ---- AI 使用分析 ----
    path('dashboard/ai-usage/', views_ai_analytics.ai_usage_overview, name='admin-ai-usage-overview'),
    path('dashboard/ai-usage/trend/', views_ai_analytics.ai_usage_trend, name='admin-ai-usage-trend'),
    path('dashboard/ai-usage/by-function/', views_ai_analytics.ai_usage_by_function, name='admin-ai-usage-by-function'),
    path('dashboard/ai-usage/by-user/', views_ai_analytics.ai_usage_by_user, name='admin-ai-usage-by-user'),
    path('dashboard/ai-usage/function-trend/', views_ai_analytics.ai_usage_function_trend, name='admin-ai-usage-function-trend'),
    path('dashboard/ai-usage/token-distribution/', views_ai_analytics.ai_usage_token_distribution, name='admin-ai-usage-token-distribution'),
    path('dashboard/ai-usage/features/', views_ai_analytics.ai_usage_features, name='admin-ai-usage-features'),

    # ---- 业务数据（通用集合资源）----
    path('exams/', views_data.resource_list, {'name': 'exams'}),
    path('exams/bulk-delete/', views_data.resource_bulk_delete, {'name': 'exams'}),
    path('exams/<str:doc_id>/', views_data.resource_detail, {'name': 'exams'}),

    path('subjects/', views_data.resource_list, {'name': 'subjects'}),
    path('subjects/bulk-delete/', views_data.resource_bulk_delete, {'name': 'subjects'}),
    path('subjects/<str:doc_id>/', views_data.resource_detail, {'name': 'subjects'}),

    # 题目批量导入（注意：必须放在 questions/<str:doc_id>/ 之前，避免被通配截获）
    path('questions/import/', views_import.import_create, name='admin-import-create'),
    path('questions/import/excel/', views_import.import_excel, name='admin-import-excel'),
    path('questions/import/templates/', views_import.import_templates, name='admin-import-templates'),
    path('questions/import/templates/<str:qtype>/', views_import.import_template_download, name='admin-import-template-download'),
    path('questions/import/<int:job_id>/', views_import.import_detail, name='admin-import-detail'),

    path('questions/', views_data.resource_list, {'name': 'questions'}),
    path('questions/bulk-delete/', views_data.resource_bulk_delete, {'name': 'questions'}),
    path('questions/<str:doc_id>/tags/', question_tags_dispatch, name='admin-question-tags'),
    path('questions/<str:doc_id>/ai-grade/', views_import.ai_grade, name='admin-ai-grade'),
    path('questions/<str:doc_id>/', views_data.resource_detail, {'name': 'questions'}),

    # ---- 标签管理 ----
    path('tags/', views_tags.tag_list, name='admin-tag-list'),
    path('tags/bind/', views_tags.tags_batch_bind, name='admin-tag-bind'),
    path('tags/<int:pk>/stats/', views_tags.tag_stats, name='admin-tag-stats'),
    path('tags/<int:pk>/', views_tags.tag_detail, name='admin-tag-detail'),

    # ---- 图片上传 ----
    path('upload/', views_import.upload_image, name='admin-upload'),

    path('records/', views_data.resource_list, {'name': 'records'}),
    path('records/bulk-delete/', views_data.resource_bulk_delete, {'name': 'records'}),
    path('records/<str:doc_id>/', views_data.resource_detail, {'name': 'records'}),

    path('notes/', views_data.resource_list, {'name': 'notes'}),
    path('notes/bulk-delete/', views_data.resource_bulk_delete, {'name': 'notes'}),
    path('notes/stats/', views_data.notes_stats, name='admin-notes-stats'),
    path('notes/<str:doc_id>/', views_data.resource_detail, {'name': 'notes'}),

    # ---- 知识库 ----
    path('knowledge/', views_data.resource_list, {'name': 'knowledge'}),
    path('knowledge/bulk-delete/', views_data.resource_bulk_delete, {'name': 'knowledge'}),
    path('knowledge/<str:doc_id>/', views_data.resource_detail, {'name': 'knowledge'}),

    # ---- 学习笔记 ----
    path('studynotes/', views_data.resource_list, {'name': 'studynotes'}),
    path('studynotes/bulk-delete/', views_data.resource_bulk_delete, {'name': 'studynotes'}),
    path('studynotes/<str:doc_id>/', views_data.resource_detail, {'name': 'studynotes'}),

    # ---- 文章管理 ----
    path('articles/', views_data.resource_list, {'name': 'articles'}),
    path('articles/bulk-delete/', views_data.resource_bulk_delete, {'name': 'articles'}),
    # 文章 <-> 知识库索引（注意：批量路由必须放在 articles/<doc_id>/ 之前）
    path('articles/to-knowledge/', views_ai.kb_articles_batch_link, name='admin-articles-to-knowledge'),
    path('articles/<str:doc_id>/to-knowledge/', views_ai.kb_article_link, name='admin-article-to-knowledge'),
    path('articles/<str:doc_id>/audit/', views_data.article_audit, name='article-audit'),
    path('articles/<str:doc_id>/', views_data.resource_detail, {'name': 'articles'}),

    # ---- 应用设置 ----
    path('app-settings/', views_data.resource_list, {'name': 'app-settings'}),
    path('app-settings/bulk-delete/', views_data.resource_bulk_delete, {'name': 'app-settings'}),
    path('app-settings/<str:doc_id>/', views_data.resource_detail, {'name': 'app-settings'}),

    # ---- 激活码管理 ----
    path('activation-codes/', views_data.resource_list, {'name': 'activation-codes'}),
    path('activation-codes/bulk-delete/', views_data.resource_bulk_delete, {'name': 'activation-codes'}),
    path('activation-codes/generate/', views_data.activation_codes_generate, name='admin-activation-codes-generate'),
    path('activation-codes/<str:doc_id>/', views_data.resource_detail, {'name': 'activation-codes'}),

    # ---- AI 配置 ----
    path('ai/config/', views_ai.ai_config_dispatch, name='ai-config'),
    path('ai/test/', views_ai.ai_test, name='ai-test'),
    path('ai/assist/', views_ai.ai_assist, name='admin-ai-assist'),

    # ---- AI 多模型管理（全局模型；meta 必须在 <model_id> 之前）----
    path('ai/models/', views_ai.ai_models_dispatch, name='ai-models-dispatch'),
    path('ai/models/meta/', views_ai.ai_models_meta, name='ai-models-meta'),
    path('ai/models/<str:model_id>/', views_ai.ai_model_detail, name='ai-model-detail'),
    path('ai/models/<str:model_id>/default/', views_ai.ai_model_set_default, name='ai-model-set-default'),
    path('ai/models/<str:model_id>/test/', views_ai.ai_model_test, name='ai-model-test'),

    # ---- AI 任务管理 ----
    path('ai/jobs/', views_ai.ai_job_list, name='ai-job-list'),
    path('ai/jobs/<str:job_id>/', views_ai.ai_job_status, name='ai-job-status'),
    path('ai/jobs/<str:job_id>/cancel/', views_ai.ai_job_cancel, name='ai-job-cancel'),

    # ---- AI 题目解析 ----
    path('ai/questions/<str:doc_id>/analyze/', views_ai.question_analyze, name='ai-question-analyze'),
    path('ai/questions/analyze-batch/', views_ai.question_analyze_batch, name='ai-question-analyze-batch'),

    # ---- AI 智能组卷 ----
    path('ai/compose/', views_ai.exam_compose, name='ai-exam-compose'),
    path('ai/compose/<str:job_id>/', views_ai.compose_status, name='ai-compose-status'),
    path('ai/compose/<str:job_id>/confirm/', views_ai.compose_confirm, name='ai-compose-confirm'),

    # ---- AI 智能组卷 V2（三阶段定向组卷）----
    path('ai/smart-compose/', views_ai.smart_compose, name='ai-smart-compose'),
    path('ai/smart-compose/kp-stats/', views_ai.smart_compose_kp_stats, name='ai-smart-compose-kp-stats'),
    path('ai/smart-compose/rebuild-index/', views_ai.smart_compose_rebuild_index, name='ai-smart-compose-rebuild-index'),

    # ---- AI 智能判卷 ----
    path('ai/grade-batch/', views_ai.ai_grade_batch, name='ai-grade-batch'),
    path('ai/grade/review-list/', views_ai.ai_grade_review_list, name='ai-grade-review-list'),
    path('ai/grade/<str:history_id>/review/', views_ai.ai_grade_review, name='ai-grade-review'),

    # ---- AI P1: 试卷分析（管理端）----
    path('ai/exams/<str:examid>/analyze/', views_ai.exam_analyze, name='ai-exam-analyze'),
    path('ai/exams/<str:examid>/analysis/', views_ai.exam_analysis_result, name='ai-exam-analysis'),

    # ---- AI P1: 小程序端 AI 接口 ----
    path('ai/review-plan/', views_ai.review_plan, name='ai-review-plan'),
    path('ai/learning-profile/', views_ai.learning_profile, name='ai-learning-profile'),
    path('ai/jobs/<str:job_id>/status/', views_ai.ai_job_status_mp, name='ai-job-status-mp'),

    # ---- AI P2: 知识库 / 自动标签 / Excel 校验（管理端）----
    path('ai/kb/rebuild/', views_ai.kb_rebuild, name='ai-kb-rebuild'),
    path('ai/kb/stats/', views_ai.kb_stats, name='ai-kb-stats'),
    path('ai/kb/articles/', views_ai.kb_indexed_articles, name='ai-kb-indexed-articles'),
    path('ai/questions/auto-tag/', views_ai.question_auto_tag_batch, name='ai-question-auto-tag'),
    path('ai/questions/auto-tag-sync-batch/', views_ai.question_auto_tag_sync_batch, name='ai-question-auto-tag-sync-batch'),
    path('ai/questions/<str:doc_id>/suggest-tags/', views_ai.question_suggest_tags, name='ai-question-suggest-tags'),
    path('ai/questions/<str:doc_id>/tags/', views_ai.question_apply_tags, name='ai-question-apply-tags'),
    path('ai/questions/<str:doc_id>/auto-tag-sync/', views_ai.question_auto_tag_sync, name='ai-question-auto-tag-sync'),
    path('ai/excel-validate/', views_ai.excel_validate, name='ai-excel-validate'),

    # ---- 小程序用户 ----
    path('users/', views_data.user_list, name='admin-user-list'),
    path('users/<str:openid>/profile/', views_profile.user_profile, name='admin-user-profile'),
    path('users/<str:openid>/', views_data.user_dispatch, name='admin-user-detail'),

    # ---- 原始数据浏览 ----
    path('collections/', views_data.collection_index, name='admin-collection-index'),
    path('collections/<str:name>/', views_data.collection_docs, name='admin-collection-docs'),

    # ---- 管理员与角色 ----
    path('admins/', views_admin.admin_list, name='admin-admin-list'),
    path('admins/<int:pk>/', views_admin.admin_detail, name='admin-admin-detail'),
    path('admins/<int:pk>/reset-password/', views_admin.admin_reset_password, name='admin-reset-password'),
    path('roles/', views_admin.role_list, name='admin-role-list'),
    path('roles/<int:pk>/', views_admin.role_detail, name='admin-role-detail'),

    # 兜底：未匹配的 /api/admin/ 请求统一返回 JSON 信封
    re_path(r'^.*$', views_data.unknown_endpoint),
]
