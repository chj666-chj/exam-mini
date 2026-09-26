"""CORS 中间件 —— 本地小程序调试支持。

微信开发者工具中开启「不校验合法域名」后 wx.request 不受浏览器同源策略限制，
此中间件仅为浏览器直接调试 / 其它前端工具访问时提供跨域支持。
"""

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Openid, Authorization, X-Admin-Token',
    'Access-Control-Expose-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
}


class ApiCorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'OPTIONS' and request.path.startswith('/api/'):
            from django.http import HttpResponse
            response = HttpResponse()
        else:
            response = self.get_response(request)
        for k, v in CORS_HEADERS.items():
            response[k] = v
        return response
