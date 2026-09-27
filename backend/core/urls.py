from django.urls import path, re_path

from . import views
from adminapi.views_ai import (
    ai_assist, review_plan, learning_profile, ai_job_status_mp,
    kb_ask, learning_report, cs_chat,
    mp_ai_models, mp_ai_models_meta, mp_ai_model_detail,
    mp_ai_model_set_default, mp_ai_model_test,
    mp_vip_status, mp_question_analysis, mp_exam_summary_analysis,
)

urlpatterns = [
    path('login/', views.login, name='login'),
    path('register/', views.register, name='register'),
    path('account-login/', views.account_login, name='account-login'),
    # ---- 用户资料 & 密码管理 ----
    path('profile/', views.profile_get, name='profile-get'),
    path('profile/update/', views.profile_update, name='profile-update'),
    path('change-password/', views.change_password, name='change-password'),
    path('forgot-password/', views.forgot_password, name='forgot-password'),
    path('reset-password/', views.reset_password, name='reset-password'),
    path('ai/assist/', ai_assist, name='ai-assist'),
    path('ai/review-plan/', review_plan, name='ai-review-plan-mp'),
    path('ai/learning-profile/', learning_profile, name='ai-learning-profile-mp'),
    path('ai/jobs/<str:job_id>/status/', ai_job_status_mp, name='ai-job-status-mp-route'),
    path('ai/kb-ask/', kb_ask, name='ai-kb-ask-mp'),
    path('ai/report/', learning_report, name='ai-report-mp'),
    path('ai/cs-chat/', cs_chat, name='ai-cs-chat-mp'),
    # ---- AI 多模型管理（小程序端：全局 + 本人）----
    path('ai/models/', mp_ai_models, name='ai-models-mp'),
    path('ai/models/meta/', mp_ai_models_meta, name='ai-models-meta-mp'),
    path('ai/models/<str:model_id>/', mp_ai_model_detail, name='ai-model-detail-mp'),
    path('ai/models/<str:model_id>/default/', mp_ai_model_set_default, name='ai-model-set-default-mp'),
    path('ai/models/<str:model_id>/test/', mp_ai_model_test, name='ai-model-test-mp'),
    # ---- AI 题目解析 & 答题分析总结（VIP 专用）----
    path('ai/vip-status/', mp_vip_status, name='ai-vip-status-mp'),
    path('ai/question-analysis/<str:question_id>/', mp_question_analysis, name='ai-question-analysis-mp'),
    path('ai/exam-summary/', mp_exam_summary_analysis, name='ai-exam-summary-mp'),
    # ---- 激活码自助激活（小程序端）----
    path('activation/redeem/', views.activation_redeem, name='activation-redeem'),
    path('upload/', views.upload_image, name='upload'),
    path('ranking/', views.ranking, name='ranking'),
    path('question-stats/', views.question_stats, name='question-stats'),
    path('collections/<str:name>/', views.collection_list, name='collection-list'),
    path('collections/<str:name>/<str:doc_id>/', views.collection_detail, name='collection-detail'),
    re_path(r'^.*$', views.unknown_endpoint),
]
