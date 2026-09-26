"""全局异常处理：/api/ 路径下的 404/500 统一返回 JSON 信封。"""
from django.http import JsonResponse


def not_found_view(request, exception=None):
    if request.path.startswith('/api/'):
        return JsonResponse(
            {'code': 40401, 'message': '接口不存在', 'data': {}},
            status=404,
            json_dumps_params={'ensure_ascii': False},
        )
    return JsonResponse({'detail': 'not found'}, status=404)


def server_error_view(request):
    return JsonResponse(
        {'code': 50001, 'message': '服务内部错误', 'data': {}},
        status=500,
        json_dumps_params={'ensure_ascii': False},
    )
