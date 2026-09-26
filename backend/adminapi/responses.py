"""管理端统一响应规范。

所有 /api/admin/ 下的接口统一返回如下信封：

    {
        "code": 0,                 // 0 表示成功，非 0 见 ErrorCode
        "message": "ok",           // 可直接展示给用户的提示语
        "data": { ... }            // 业务数据；分页列表固定为
                                   // { list, total, page, page_size, total_pages }
    }

HTTP 状态码与 code 一一对应（便于网关 / 前端拦截器处理）：
    200 -> 0
    400 -> 40001 参数错误
    401 -> 40101 未登录 / 40102 令牌过期 / 40103 账号或密码错误
    403 -> 40301 无权限 / 40302 账号已停用
    404 -> 40401 资源不存在
    409 -> 40901 资源冲突
    500 -> 50001 服务内部错误
"""
from django.http import JsonResponse


class ErrorCode:
    SUCCESS = 0
    PARAM_ERROR = 40001
    UNAUTHORIZED = 40101
    TOKEN_EXPIRED = 40102
    INVALID_CREDENTIALS = 40103
    FORBIDDEN = 40301
    ACCOUNT_DISABLED = 40302
    NOT_FOUND = 40401
    CONFLICT = 40901
    BAD_GATEWAY = 50201
    SERVER_ERROR = 50001
    SERVICE_UNAVAILABLE = 50301


CODE_STATUS = {
    ErrorCode.SUCCESS: 200,
    ErrorCode.PARAM_ERROR: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.INVALID_CREDENTIALS: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.ACCOUNT_DISABLED: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.BAD_GATEWAY: 502,
    ErrorCode.SERVER_ERROR: 500,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
}


def ok(data=None, message='ok'):
    """成功响应。data 为 None 时返回空对象，保证前端 data 字段类型稳定。"""
    return JsonResponse(
        {'code': ErrorCode.SUCCESS, 'message': message, 'data': {} if data is None else data},
        json_dumps_params={'ensure_ascii': False},
    )


def fail(code=ErrorCode.SERVER_ERROR, message='请求失败', data=None, http_status=None):
    """失败响应。http_status 缺省时由错误码映射。"""
    status = http_status or CODE_STATUS.get(code, 500)
    return JsonResponse(
        {'code': code, 'message': message, 'data': {} if data is None else data},
        status=status,
        json_dumps_params={'ensure_ascii': False},
    )


def paginate(items, total, page, page_size):
    """统一分页结构。"""
    page_size = page_size or 20
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return {
        'list': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
    }


def parse_page(request, default_page=1, default_size=20, max_size=200):
    """从查询参数解析分页参数，非法值回退为默认值。"""
    try:
        page = int(request.GET.get('page', default_page))
    except (TypeError, ValueError):
        page = default_page
    try:
        page_size = int(request.GET.get('page_size', default_size))
    except (TypeError, ValueError):
        page_size = default_size
    page = max(page, 1)
    page_size = min(max(page_size, 1), max_size)
    return page, page_size
