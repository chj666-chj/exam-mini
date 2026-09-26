from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    # Web 管理端（统一 {code,message,data} 信封 + 令牌鉴权）
    # 注意必须放在 'api/' 之前，否则会被 core 的兜底路由截获
    path('api/admin/', include('adminapi.urls')),
    # 小程序端兼容层（云开发语义，保持原调用格式不变）
    path('api/', include('core.urls')),
]

# 本地开发：题目图片等媒体文件访问
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# 统一 JSON 错误信封（DEBUG=False 时由 Django 自动调用）
handler404 = 'backend.errors.not_found_view'
handler500 = 'backend.errors.server_error_view'
