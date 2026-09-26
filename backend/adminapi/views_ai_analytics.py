"""AI 使用分析看板接口。

- GET /api/admin/dashboard/ai-usage/              AI 使用概览（KPI 卡片）
- GET /api/admin/dashboard/ai-usage/trend/        调用趋势（按天）
- GET /api/admin/dashboard/ai-usage/by-function/  按功能维度汇总
- GET /api/admin/dashboard/ai-usage/by-user/      按用户维度汇总
- GET /api/admin/dashboard/ai-usage/function-trend/  按功能分类的调用趋势
- GET /api/admin/dashboard/ai-usage/token-distribution/  Token 消耗分布
- GET /api/admin/dashboard/ai-usage/features/     AI 功能清单
"""
from . import permissions as perm
from .responses import ErrorCode, fail, ok
from .ai_usage_logger import AIUsageLogger


def _parse_days(request):
    """从查询参数解析天数，缺省 30，范围 7-180。"""
    try:
        days = int(request.GET.get('days', 30))
    except (TypeError, ValueError):
        days = 30
    return max(7, min(days, 180))


@perm.require_perms('dashboard.view')
def ai_usage_overview(request):
    """GET /api/admin/dashboard/ai-usage/  AI 使用概览。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    days = _parse_days(request)
    data = AIUsageLogger.overview(days=days)
    return ok(data)


@perm.require_perms('dashboard.view')
def ai_usage_trend(request):
    """GET /api/admin/dashboard/ai-usage/trend/  调用时间趋势。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    days = _parse_days(request)
    data = AIUsageLogger.trend(days=days)
    return ok(data)


@perm.require_perms('dashboard.view')
def ai_usage_by_function(request):
    """GET /api/admin/dashboard/ai-usage/by-function/  按功能维度汇总。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    days = _parse_days(request)
    data = AIUsageLogger.by_function(days=days)
    return ok(data)


@perm.require_perms('dashboard.view')
def ai_usage_by_user(request):
    """GET /api/admin/dashboard/ai-usage/by-user/  按用户维度汇总。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    days = _parse_days(request)
    try:
        top_n = int(request.GET.get('top_n', 20))
    except (TypeError, ValueError):
        top_n = 20
    top_n = max(5, min(top_n, 100))
    data = AIUsageLogger.by_user(days=days, top_n=top_n)
    return ok(data)


@perm.require_perms('dashboard.view')
def ai_usage_function_trend(request):
    """GET /api/admin/dashboard/ai-usage/function-trend/  按功能分类的调用趋势。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    days = _parse_days(request)
    data = AIUsageLogger.function_trend(days=days)
    return ok(data)


@perm.require_perms('dashboard.view')
def ai_usage_token_distribution(request):
    """GET /api/admin/dashboard/ai-usage/token-distribution/  Token 消耗分布。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    days = _parse_days(request)
    data = AIUsageLogger.token_by_function(days=days)
    return ok(data)


@perm.require_perms('dashboard.view')
def ai_usage_features(request):
    """GET /api/admin/dashboard/ai-usage/features/  AI 功能清单。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    data = AIUsageLogger.features()
    return ok(data)
