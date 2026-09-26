# 考试宝系统四阶段测试方案

> QA工程师：严过关  
> 测试对象：考试宝在线考试备考平台（Django后端 + Vue3管理后台 + 微信小程序）  
> 测试环境：后端 localhost:8000 / 管理后台 localhost:5173 / SQLite  

---

## 一、白盒测试

### 1.1 测试目标

通过代码审查与静态分析，识别后端源码中的逻辑错误、安全漏洞、数据一致性隐患及前后端契约不一致问题，在未运行代码的前提下发现潜在缺陷。

### 1.2 测试范围

| 模块 | 文件路径 | 审查重点 |
|------|---------|---------|
| 小程序端核心API | `core/views.py` | 集合白名单、写权限校验、`__contains` SQL拼接、文章浏览量自增竞态 |
| 管理端认证 | `adminapi/views_auth.py` | 登录限流、密码校验、令牌管理 |
| 管理端权限 | `adminapi/permissions.py` | 权限点定义、装饰器逻辑、`require_perms`的methods参数 |
| 管理端数据 | `adminapi/views_data.py` | 通用CRUD校验、用户管理权限层级、批量删除 |
| 用户画像 | `adminapi/views_profile.py` | 题型错误率统计逻辑、排名计算、掌握度评级 |
| AI服务 | `adminapi/views_ai.py` | apiKey脱敏与更新逻辑、LLM调用异常处理 |
| 题库导入 | `adminapi/views_import.py` | 导入去重、异步线程安全、Excel解析 |
| 数据看板 | `adminapi/views_dashboard.py` | 窗口统计、趋势计算、新用户判定 |
| 数据工具 | `adminapi/data_utils.py` | 类型归一、时间解析、正确率计算 |
| 题目Schema | `adminapi/question_schema.py` | 题型识别、选项归一化、重复检测键 |
| 响应规范 | `adminapi/responses.py` | 错误码映射、分页逻辑 |
| 标签管理 | `adminapi/views_tags.py` | 标签CRUD、批量绑定、同步镜像 |
| 中间件 | `core/middleware.py` | CORS配置安全性 |
| 全局配置 | `backend/settings.py` | SECRET_KEY暴露、DEBUG模式、ALLOWED_HOSTS |

### 1.3 测试用例

| 用例ID | 描述 | 前置条件 | 审查输入（代码位置） | 预期结果 | 优先级 |
|--------|------|---------|-------------------|---------|--------|
| WB-01 | `__contains`查询SQL注入风险验证 | 无 | `core/views.py` L148-157：`field = key.split('__contains')[0]`，`field`直接拼入`json_extract(data, '$." + field + "')` SQL语句，未做任何转义或白名单校验 | **确认存在SQL注入风险**：攻击者可通过构造查询参数key如 `a') OR 1=1 --__contains` 注入恶意SQL。需修复为对field做白名单校验或参数化查询 | P0 |
| WB-02 | 文章浏览量自增竞态条件验证 | articles集合存在文档 | `core/views.py` L224-226：`obj.data['views'] = obj.data.get('views', 0) + 1; obj.save()`，读-改-写无事务/锁保护 | **确认存在竞态条件**：并发GET请求会导致浏览量丢失增量。应改用`F()`表达式或`update()`原子操作 | P1 |
| WB-03 | AI配置PUT空apiKey清空配置验证 | AI配置已存在有效apiKey | `adminapi/views_ai.py` L146-152：当`body['apiKey']`为空字符串`''`时，不满足`startswith('****')`条件，执行`new_config['apiKey'] = ''`，将清空已有Key | **确认存在缺陷**：空字符串应视为"不修改"而非"清空"。需增加空字符串判断：`if incoming_key == '': pass` | P1 |
| WB-04 | 题型错误率统计可能永远为空验证 | 用户存在答题记录，记录中items/questions字段含题目数据 | `adminapi/views_profile.py` L380-403：`_build_weakness_stats`遍历`r.get('questions', [])`中的题目对象，通过`q.get('right')`判断对错。若答题记录中题目对象的正确性字段名不是`right`（如`isRight`/`correct`），则`du.to_number(q.get('right'), 0)`恒返回0，所有题目被判为"错误"，error_rate恒为1.0 | **确认存在逻辑缺陷**：需与小程序端确认题目对象字段名，统一`right`字段或做兼容映射 | P1 |
| WB-05 | 小程序同秒交卷答题记录覆盖验证 | 同一用户在同一秒内提交两次答题记录 | `core/views.py` L192-197：`doc_id = data.pop('_id', None)`，若小程序用时间戳生成`_id`（如`20250101120000`），同秒提交的`_id`相同，`update_or_create`会覆盖前一条记录 | **确认存在数据丢失风险**：需在小程序端确保`_id`唯一性（追加随机数），或后端用`create`而非`update_or_create` | P1 |
| WB-06 | 用户管理接口权限层级不精确验证 | 存在仅拥有`user.view`权限的管理员账号 | `adminapi/views_data.py` L672：`user_dispatch`装饰器仅检查`user.view`，写操作(PUT/PATCH/DELETE)在函数内部通过`_can_manage`检查`user.manage`。装饰器未使用`methods`参数区分读写权限 | **确认权限层级不精确**：`user.view`用户可到达写操作入口再被403拦截，应使用`@require_perms('user.view', 'user.manage', methods=WRITE_METHODS)`在装饰器层拦截 | P2 |
| WB-07 | `as_obj`函数JSON字符串解析失败验证 | 文档字段被存为JSON字符串（含`true`/`false`/`null`） | `adminapi/data_utils.py` L55-66：`as_obj`使用`ast.literal_eval`解析字符串，但JSON的`true`/`false`/`null`不是合法的Python字面量，会抛出`ValueError`被捕获返回`None` | **确认存在兼容性缺陷**：应改用`json.loads`替代`ast.literal_eval`，或在`ast.literal_eval`失败后fallback到`json.loads` | P1 |
| WB-08 | 登录失败限流进程内计数重启清零验证 | 服务重启后立即尝试暴力破解 | `adminapi/views_auth.py` L13-14：`_LOGIN_FAILS = {}`为模块级变量，进程重启后清零，攻击者可通过频繁重启绕过限流 | **确认为已知限制**：本地开发环境可接受，生产环境需换Redis。代码注释已说明 | P3 |
| WB-09 | `parse_datetime`微秒格式截断逻辑验证 | 时间字符串含微秒后缀 | `adminapi/data_utils.py` L111：`text[:len(fmt) + 8] if fmt.endswith('%f')`，对`%f`格式的截断长度计算为`len(fmt) + 8`，可能截断不足或过度 | **需验证**：`%Y-%m-%dT%H:%M:%S.%f`长度为26，`len(fmt)=26`，`26+8=34`，截取`text[:34]`，对正常微秒时间戳（如`2025-01-01T12:00:00.123456`长度25）足够。但若微秒位数不标准可能出问题 | P3 |
| WB-10 | `require_perms`装饰器`methods`参数逻辑验证 | 管理员拥有`.view`权限但缺少`.manage`权限 | `adminapi/permissions.py` L175-177：当`request.method.upper() not in methods`时，`needed`过滤掉`.manage`权限。但当`methods`为None时（如`resource_list`的`@require_perms()`无参调用），所有方法都不校验权限 | **确认`resource_list`和`resource_detail`的`@require_perms()`无参数调用**：权限检查依赖`_resource`函数内部手动校验`config['view']`，装饰器仅做登录校验。逻辑可工作但不够显式 | P2 |
| WB-11 | `name_of`函数硬编码单复数转换验证 | 资源名为`studynotes`或`knowledge` | `adminapi/views_data.py` L295-299：`key.rstrip('s')`对`studynotes`得到`studynote`，对`knowledge`得到`knowledge`（无尾s不变），对`exams`特殊处理为`exam`。但`records`→`record`、`notes`→`note`也依赖`rstrip('s')` | **确认逻辑脆弱**：若新增资源名不以s结尾或以`is`/`es`结尾，`rstrip('s')`会产生错误结果。建议用显式映射表 | P3 |
| WB-12 | SECRET_KEY硬编码与DEBUG=True安全隐患 | 生产部署 | `backend/settings.py` L13-14：`SECRET_KEY = 'django-insecure-...'`，`DEBUG = True`，`ALLOWED_HOSTS = ['*']` | **确认安全隐患**：仅限本地开发，生产部署前必须修改。代码注释已标注`local-dev-only` | P3 |

### 1.4 测试方法

1. **人工代码审查**：逐文件阅读源码，对照业务逻辑检查数据流、控制流、异常处理
2. **静态安全分析**：重点检查SQL拼接（`.extra()`）、用户输入直接拼入查询、密码处理、CORS配置
3. **数据流追踪**：从小程序端API请求 → 中间件 → 视图函数 → 模型操作，验证数据完整性与权限控制
4. **前后端契约比对**：对照管理后台Vue组件中的API调用与后端路由/响应格式

### 1.5 预期结果

- P0级问题（SQL注入）必须立即修复
- P1级问题（竞态条件、空值清空、字段不兼容、数据覆盖）需在发版前修复
- P2级问题（权限层级、装饰器显式性）建议优化
- P3级问题（开发环境限制）记录为已知问题，生产部署时处理
- 输出《白盒测试问题清单》，包含代码位置、复现步骤、修复建议

---

## 二、黑盒测试

### 2.1 测试目标

在不查看内部代码实现的前提下，通过API接口调用验证系统功能正确性，覆盖正常流程、异常输入、边界条件与安全场景。

### 2.2 测试范围

| 模块 | API端点 | 测试重点 |
|------|---------|---------|
| 小程序登录 | `POST /api/login/` | 返回openid格式、默认openid逻辑 |
| 小程序集合查询 | `GET /api/collections/<name>/` | 白名单校验、字段过滤、计数模式、articles默认过滤 |
| 小程序集合写入 | `POST /api/collections/<name>/` | 写权限校验、_openid注入、articles默认字段 |
| 小程序文档操作 | `GET/PUT/DELETE /api/collections/<name>/<id>/` | 按ID读取、归属校验、文章浏览量自增 |
| 小程序图片上传 | `POST /api/upload/` | 格式校验、大小限制 |
| 小程序AI辅助 | `POST /api/ai/assist/` | 参数校验、AI开关校验 |
| 管理端认证 | `POST /api/admin/auth/login/` | 正确/错误凭证、停用账号、限流 |
| 管理端认证 | `POST /api/admin/auth/password/` | 修改密码、旧密码校验、新密码长度 |
| 管理端看板 | `GET /api/admin/dashboard/*` | 概览数据、趋势参数、排名、日志分页 |
| 管理端考试CRUD | `GET/POST/PUT/DELETE /api/admin/exams/*` | 校验规则、批量删除、分页 |
| 管理端科目CRUD | `GET/POST/PUT/DELETE /api/admin/subjects/*` | 必填校验、pid过滤 |
| 管理端题目CRUD | `GET/POST/PUT/DELETE /api/admin/questions/*` | 题型校验、选项校验、批量删除 |
| 管理端题库导入 | `POST /api/admin/questions/import/` | JSON导入、重复策略、异步模式 |
| 管理端Excel导入 | `POST /api/admin/questions/import/excel/` | 文件格式、题型校验、解析结果 |
| 管理端标签管理 | `GET/POST/PUT/DELETE /api/admin/tags/*` | 分类校验、重名冲突、批量绑定 |
| 管理端文章管理 | `GET/POST/PUT/DELETE /api/admin/articles/*` | 状态枚举、图片/标签数量限制 |
| 管理端文章审核 | `POST /api/admin/articles/<id>/audit/` | 审核动作、拒绝原因 |
| 管理端AI配置 | `GET/PUT /api/admin/ai/config/` | apiKey脱敏、空值处理 |
| 管理端用户管理 | `GET/PUT/DELETE /api/admin/users/*` | 用户列表、画像、停用、删除 |
| 管理端管理员管理 | `GET/POST/PUT/DELETE /api/admin/admins/*` | 创建、停用、角色修改、自我保护 |
| 管理端角色管理 | `GET/PUT /api/admin/roles/*` | 权限编辑、超级管理员保护 |

### 2.3 测试用例

#### 2.3.1 小程序端API

| 用例ID | 描述 | 前置条件 | 输入 | 预期输出 | 优先级 |
|--------|------|---------|------|---------|--------|
| BB-01 | 模拟登录获取openid | 服务正常运行 | `POST /api/login/`，无请求体 | 200，返回`{"openid": "xxx"}`，openid为非空字符串 | P0 |
| BB-02 | 查询白名单内集合并过滤 | questions集合存在数据 | `GET /api/collections/questions/?examid=001001` | 200，返回`{"data": [...]}`，所有文档examid=001001 | P0 |
| BB-03 | 查询白名单外集合 | 无 | `GET /api/collections/users/` | 404，返回`{"code": 40401, "message": "集合 users 不在白名单中"}` | P0 |
| BB-04 | 集合计数模式 | historys集合存在数据 | `GET /api/collections/historys/?count=1` | 200，返回`{"total": <number>}`，total为非负整数 | P1 |
| BB-05 | articles默认只返回已发布 | articles集合含pending和published状态文档 | `GET /api/collections/articles/`（不带status参数） | 200，返回的data中所有文档status=published | P1 |
| BB-06 | articles指定status过滤 | articles集合含多种状态 | `GET /api/collections/articles/?status=pending` | 200，返回的data中所有文档status=pending | P1 |
| BB-07 | 私有集合写入无openid拒绝 | EXAM_REQUIRE_OPENID_FOR_WRITE=True | `POST /api/collections/historys/`，Body: `{"key":"val"}`，无X-Openid头 | 403，返回`{"code": 40301, "message": "未登录..."}` | P0 |
| BB-08 | 私有集合写入有openid成功 | 已通过login获取openid | `POST /api/collections/historys/`，Header: `X-Openid: test-001`，Body: `{"rightNum": 5}` | 200，返回`{"_id": "xxx"}`，文档含_openid=test-001 | P0 |
| BB-09 | 非私有集合写入无需openid | 无 | `POST /api/collections/questions/`，Body: `{"title":"测试题","examid":"001"}` | 200，返回`{"_id": "xxx"}` | P1 |
| BB-10 | 按ID获取文档 | 存在doc_id为"test-doc-001"的文档 | `GET /api/collections/questions/test-doc-001/` | 200，返回`{"data": {..., "_id": "test-doc-001"}}` | P0 |
| BB-11 | 不存在的文档ID | 无 | `GET /api/collections/questions/non-existent-id/` | 404，返回`{"code": 40401, "message": "文档不存在"}` | P1 |
| BB-12 | 删除他人文档被拒绝 | 文档_openid为user-A，请求者openid为user-B | `DELETE /api/collections/historys/doc-001/`，Header: `X-Openid: user-B` | 403，返回`{"code": 40301, "message": "无权限..."}` | P0 |
| BB-13 | PUT更新文档保留_openid | 文档_openid为user-A | `PUT /api/collections/historys/doc-001/`，Header: `X-Openid: user-A`，Body: `{"newField": 1, "_openid": "hacker"}` | 200，文档_openid仍为user-A，不被篡改 | P1 |
| BB-14 | 图片上传格式校验 | 无 | `POST /api/upload/`，上传.txt文件 | 400，返回`{"code": 40001, "message": "仅支持 jpg/png/gif/webp 格式"}` | P1 |
| BB-15 | 图片上传大小超限 | 无 | `POST /api/upload/`，上传6MB的.jpg文件 | 400，返回`{"code": 40001, "message": "图片大小不能超过 5MB"}` | P1 |
| BB-16 | 图片上传成功 | 无 | `POST /api/upload/`，上传1MB的.png文件 | 200，返回`{"url": "/media/uploads/...", "name": "...", "size": ...}` | P1 |
| BB-17 | AI辅助写作-prompt为空 | 无 | `POST /api/ai/assist/`，Body: `{"prompt": ""}` | 400，返回`{"code": 40001, "message": "请输入文章标题或主题"}` | P1 |
| BB-18 | AI辅助写作-AI未启用 | AI配置enabled=false | `POST /api/ai/assist/`，Body: `{"prompt": "测试主题"}` | 400，返回`{"code": 40001, "message": "AI 功能未启用..."}` | P1 |
| BB-19 | `__contains`数组包含查询 | questions集合文档tags字段为数组 | `GET /api/collections/questions/?tags__contains=基础知识` | 200，返回data中所有文档的tags数组包含"基础知识" | P2 |
| BB-20 | 未知API端点兜底 | 无 | `GET /api/unknown-endpoint/` | 404，返回`{"code": 40401, "message": "接口不存在"}` | P2 |

#### 2.3.2 管理端API — 认证模块

| 用例ID | 描述 | 前置条件 | 输入 | 预期输出 | 优先级 |
|--------|------|---------|------|---------|--------|
| BB-21 | 正确凭证登录 | 存在admin/admin123账号 | `POST /api/admin/auth/login/`，Body: `{"username":"admin","password":"admin123"}` | 200，`{"code":0, "data":{"token":"...", "user":{...}}}` | P0 |
| BB-22 | 错误密码登录 | 存在admin账号 | `POST /api/admin/auth/login/`，Body: `{"username":"admin","password":"wrong"}` | 401，`{"code":40103, "message":"账号或密码错误"}` | P0 |
| BB-23 | 空用户名登录 | 无 | `POST /api/admin/auth/login/`，Body: `{"username":"","password":"123"}` | 400，`{"code":40001, "message":"账号与密码不能为空"}` | P1 |
| BB-24 | 连续5次错误后锁定 | 存在admin账号 | 连续5次`POST /api/admin/auth/login/`密码错误，第6次尝试 | 403，`{"code":40301, "message":"连续输错密码 5 次..."}` | P1 |
| BB-25 | 无Token访问受保护接口 | 无 | `GET /api/admin/auth/profile/`，无Authorization头 | 401，`{"code":40101, "message":"未登录或缺少令牌"}` | P0 |
| BB-26 | 无效Token访问 | 无 | `GET /api/admin/auth/profile/`，Header: `Authorization: Bearer invalid-token` | 401，`{"code":40101, "message":"令牌无效..."}` | P0 |
| BB-27 | 修改密码-旧密码错误 | 已登录 | `POST /api/admin/auth/password/`，Body: `{"old_password":"wrong","new_password":"newpass123"}` | 401，`{"code":40103, "message":"原密码不正确"}` | P1 |
| BB-28 | 修改密码-新密码过短 | 已登录 | `POST /api/admin/auth/password/`，Body: `{"old_password":"admin123","new_password":"123"}` | 400，`{"code":40001, "message":"新密码至少 6 位"}` | P1 |
| BB-29 | 修改密码成功后旧Token失效 | 已登录，持有Token-A | `POST /api/admin/auth/password/`成功修改密码后，用Token-A访问`GET /api/admin/auth/profile/` | 修改返回200；后续Token-A访问返回401（已被清除） | P1 |
| BB-30 | 获取权限树 | 已登录 | `GET /api/admin/auth/permissions/` | 200，返回按分组组织的权限点数组 | P1 |

#### 2.3.3 管理端API — 业务CRUD模块

| 用例ID | 描述 | 前置条件 | 输入 | 预期输出 | 优先级 |
|--------|------|---------|------|---------|--------|
| BB-31 | 新增考试-正常 | 已登录且有exam.manage权限 | `POST /api/admin/exams/`，Body含name/code/status/duration等 | 200，`{"code":0, "data":{"_id":"xxx"}}` | P0 |
| BB-32 | 新增考试-缺少必填字段name | 已登录 | `POST /api/admin/exams/`，Body: `{"code":"TEST001"}`（无name） | 400，`{"code":40001, "message":"缺少必填字段：name"}` | P0 |
| BB-33 | 新增考试-及格分超过总分 | 已登录 | `POST /api/admin/exams/`，Body含name, passScore=80, totalScore=50 | 400，`{"code":40001, "message":"及格分不能超过总分"}` | P1 |
| BB-34 | 新增考试-状态枚举非法 | 已登录 | `POST /api/admin/exams/`，Body含name, status="invalid" | 400，`{"code":40001, "message":"status 必须是 draft, published, archived 之一"}` | P1 |
| BB-35 | 考试列表-关键词搜索 | 存在多条考试数据 | `GET /api/admin/exams/?keyword=测试&page=1&page_size=10` | 200，分页结构`{list, total, page, page_size, total_pages}` | P1 |
| BB-36 | 考试列表-重复_id冲突 | 已存在_id为EXAM_001的考试 | `POST /api/admin/exams/`，Body含`"_id":"EXAM_001"` | 409，`{"code":40901, "message":"该 _id 已存在：EXAM_001"}` | P1 |
| BB-37 | 更新考试-PUT全量替换 | 存在考试EXAM_001 | `PUT /api/admin/exams/EXAM_001/`，Body含name等字段 | 200，`{"code":0, "data":{"_id":"EXAM_001"}}` | P0 |
| BB-38 | 更新考试-PATCH局部更新 | 存在考试EXAM_001 | `PATCH /api/admin/exams/EXAM_001/`，Body: `{"status":"published"}` | 200，文档status变为published，其他字段不变 | P1 |
| BB-39 | 删除考试 | 存在考试EXAM_001 | `DELETE /api/admin/exams/EXAM_001/` | 200，`{"code":0, "data":{"deleted":true}}` | P0 |
| BB-40 | 批量删除考试 | 存在EXAM_001, EXAM_002 | `POST /api/admin/exams/bulk-delete/`，Body: `{"ids":["EXAM_001","EXAM_002"]}` | 200，`{"code":0, "data":{"deleted":2}}` | P1 |
| BB-41 | 新增题目-选项少于2个 | 已登录 | `POST /api/admin/questions/`，Body含examid, options仅1个选项 | 400，`{"code":40001, "message":"选项至少需要 2 个"}` | P1 |
| BB-42 | 新增题目-无正确答案 | 已登录 | `POST /api/admin/questions/`，Body含examid, options无value=1的选项 | 400，`{"code":40001, "message":"请至少指定一个正确答案..."}` | P1 |
| BB-43 | 题库导入-JSON正常 | 已登录且有question.import权限 | `POST /api/admin/questions/import/`，Body含items数组（2道单选题） | 200，`{"code":0, "data":{"status":"success", "succeeded":2}}` | P0 |
| BB-44 | 题库导入-超过上限 | 已登录 | `POST /api/admin/questions/import/`，Body含501道题 | 400，`{"code":40001, "message":"单次最多导入 500 道题目"}` | P1 |
| BB-45 | 题库导入-重复策略skip | 已存在相同题目 | `POST /api/admin/questions/import/`，on_duplicate=skip，含重复题 | 200，重复题status=skipped，skipped计数增加 | P1 |
| BB-46 | 文章新增-images超过3张 | 已登录 | `POST /api/admin/articles/`，Body含title, images为4个URL | 400，`{"code":40001, "message":"images 最多 3 张"}` | P1 |
| BB-47 | 文章审核-发布 | 存在pending状态文章 | `POST /api/admin/articles/ARTICLE_001/audit/`，Body: `{"action":"publish"}` | 200，文章status变为published | P0 |
| BB-48 | 文章审核-拒绝含原因 | 存在pending状态文章 | `POST /api/admin/articles/ARTICLE_001/audit/`，Body: `{"action":"reject","reason":"内容不合规"}` | 200，文章status=rejected，含rejectReason | P1 |
| BB-49 | 文章审核-非法action | 存在文章 | `POST /api/admin/articles/ARTICLE_001/audit/`，Body: `{"action":"invalid"}` | 400，`{"code":40001, "message":"action 必须是 publish / reject / takedown 之一"}` | P1 |

#### 2.3.4 管理端API — AI配置与用户管理

| 用例ID | 描述 | 前置条件 | 输入 | 预期输出 | 优先级 |
|--------|------|---------|------|---------|--------|
| BB-50 | 获取AI配置-apiKey脱敏 | AI配置apiKey为`sk-abcdefgh123456` | `GET /api/admin/ai/config/` | 200，apiKey显示为`****3456`，非明文 | P0 |
| BB-51 | 更新AI配置-脱敏apiKey保留原值 | 已配置apiKey | `PUT /api/admin/ai/config/`，Body: `{"apiKey":"****3456"}` | 200，apiKey保持原值不变 | P0 |
| BB-52 | 更新AI配置-空apiKey清空（已知缺陷） | 已配置apiKey=`sk-test123` | `PUT /api/admin/ai/config/`，Body: `{"apiKey":""}` | **预期（正确行为）**：apiKey应保持原值不变。**实际（缺陷）**：apiKey被清空为空字符串 | P1 |
| BB-53 | AI连接测试-未启用 | AI配置enabled=false | `POST /api/admin/ai/test/` | 400，`{"code":40001, "message":"AI 功能未启用..."}` | P1 |
| BB-54 | 用户列表-关键词搜索 | 存在用户数据 | `GET /api/admin/users/?keyword=test&page=1` | 200，分页结构，列表项含openid/nickname/records等 | P1 |
| BB-55 | 用户画像-不存在用户 | 无 | `GET /api/admin/users/non-existent-openid/profile/` | 404，`{"code":40401, "message":"用户不存在或无答题数据"}` | P1 |
| BB-56 | 停用用户-小程序端写入被拒 | 用户status=disabled | 先`PUT /api/admin/users/<openid>/`设status=disabled，再`POST /api/collections/historys/`带该openid | 小程序写入返回403，`{"code":40301, "message":"账号已停用..."}` | P0 |
| BB-57 | 删除用户-非超管被拒 | 登录账号为operator角色 | `DELETE /api/admin/users/<openid>/` | 403，`{"code":40301, "message":"删除用户数据仅超级管理员可执行"}` | P0 |
| BB-58 | 管理员自我停用被拒 | 已登录admin账号 | `PUT /api/admin/admins/<self_id>/`，Body: `{"status":"disabled"}` | 400，`{"code":40001, "message":"不能停用当前登录的账号"}` | P1 |
| BB-59 | 管理员删除自己被拒 | 已登录admin账号 | `DELETE /api/admin/admins/<self_id>/` | 400，`{"code":40001, "message":"不能删除当前登录的账号"}` | P1 |
| BB-60 | 角色权限编辑-超级管理员必须全权限 | 已登录超管 | `PUT /api/admin/roles/<superadmin_role_id>/`，Body: `{"permissions":["dashboard.view"]}`（缺少大部分权限） | 400，`{"code":40001, "message":"超级管理员角色必须拥有全部权限"}` | P1 |

### 2.4 测试方法

1. **API调用测试**：使用curl/Python脚本/Postman对每个API发送请求，验证响应状态码与JSON结构
2. **参数变异**：对必填字段传空值/超长字符串/特殊字符/类型不匹配值
3. **权限测试**：使用不同角色（superadmin/operator/viewer）的Token访问同一接口，验证权限隔离
4. **边界测试**：分页page=0、page_size=0、page_size=999、keyword含SQL特殊字符

### 2.5 预期结果

- P0用例全部通过（核心功能可用、安全校验有效）
- P1用例90%以上通过（业务校验、异常处理正确）
- P2用例80%以上通过（边界条件、兼容性）
- 已知缺陷（BB-52空apiKey清空）记录为待修复项
- 输出《黑盒测试结果汇总》，含每个用例的通过/失败状态与实际响应

---

## 三、单元测试

### 3.1 测试目标

针对后端核心函数、工具类和模型方法编写可自动执行的单元测试，验证数据处理逻辑的正确性与健壮性。

### 3.2 测试范围

| 模块 | 文件 | 被测函数/类 |
|------|------|-----------|
| 数据工具 | `adminapi/data_utils.py` | `to_text`, `to_number`, `as_obj`, `parse_datetime`, `doc_time`, `accuracy_of`, `subject_name` |
| 响应工具 | `adminapi/responses.py` | `ok`, `fail`, `paginate`, `parse_page`, `ErrorCode` |
| 权限工具 | `adminapi/permissions.py` | `is_valid_permission`, `permission_options`, `_extract_token`, `issue_token` |
| 题目Schema | `adminapi/question_schema.py` | `infer_qtype`, `normalize_question`, `duplicate_key`, `_normalize_options`, `_judge_options` |
| Markdown工具 | `adminapi/markdown_utils.py` | `extract_images`, `validate_markdown`, `strip_markdown`, `normalize_title` |
| 文档模型 | `core/models.py` | `Document.to_client()` |
| 管理员模型 | `adminapi/models.py` | `AdminUser.set_password`, `check_password`, `is_superuser`, `permissions`, `has_perm`, `to_client` |
| 令牌模型 | `adminapi/models.py` | `AdminToken.is_expired` |
| 导入任务模型 | `adminapi/models.py` | `ImportJob.progress`, `to_client` |
| 角色模型 | `adminapi/models.py` | `Role.clean_permissions`, `ensure_default_roles` |
| Excel工具 | `adminapi/excel_import.py` | `generate_template`, `parse_excel`, `_resolve_tag_names` |

### 3.3 测试用例

| 用例ID | 描述 | 前置条件 | 输入 | 预期输出 | 优先级 |
|--------|------|---------|------|---------|--------|
| UT-01 | `to_text`-字符串直接返回 | 无 | `to_text("hello")` | `"hello"` | P1 |
| UT-02 | `to_text`-字典提取name | 无 | `to_text({"name": "测试", "title": "标题"})` | `"测试"`（优先取name） | P1 |
| UT-03 | `to_text`-None返回默认值 | 无 | `to_text(None, default="N/A")` | `"N/A"` | P1 |
| UT-04 | `to_number`-整数字符串 | 无 | `to_number("42")` | `42`（int） | P1 |
| UT-05 | `to_number`-浮点字符串 | 无 | `to_number("3.14")` | `3.14`（float） | P1 |
| UT-06 | `to_number`-布尔值转整数 | 无 | `to_number(True)` | `1`（int） | P2 |
| UT-07 | `to_number`-无效值返回默认 | 无 | `to_number("abc", default=-1)` | `-1` | P1 |
| UT-08 | `as_obj`-列表直接返回 | 无 | `as_obj([1, 2, 3])` | `[1, 2, 3]` | P1 |
| UT-09 | `as_obj`-Python repr字符串解析 | 无 | `as_obj("{'key': 'val'}")` | `{'key': 'val'}` | P1 |
| UT-10 | `as_obj`-JSON字符串含true/false解析失败 | 无 | `as_obj('[{"right": true}]')` | `None`（`ast.literal_eval`无法解析JSON布尔值）—— **已知缺陷** | P1 |
| UT-11 | `parse_datetime`-标准日期时间格式 | 无 | `parse_datetime("2025/01/15 14:30")` | timezone-aware datetime（2025-01-15 14:30:00） | P1 |
| UT-12 | `parse_datetime`-14位时间戳 | 无 | `parse_datetime("20250115143000")` | timezone-aware datetime（2025-01-15 14:30:00） | P1 |
| UT-13 | `parse_datetime`-13位Unix毫秒时间戳 | 无 | `parse_datetime(1736930400000)` | 对应timezone-aware datetime | P2 |
| UT-14 | `parse_datetime`-空值返回None | 无 | `parse_datetime(None)` / `parse_datetime("")` | `None` | P1 |
| UT-15 | `accuracy_of`-正常计算 | 无 | `accuracy_of({"rightNum": 8, "items": [1,2,3,4,5,6,7,8,9,10]})` | `0.8`（8/10） | P1 |
| UT-16 | `accuracy_of`-无答题数据返回None | 无 | `accuracy_of({"rightNum": 0, "items": []})` | `None` | P1 |
| UT-17 | `accuracy_of`-正确率上限1.0 | 无 | `accuracy_of({"rightNum": 15, "items": [1,2,3]})` | `1.0`（被`min(1.0, ...)`截断） | P2 |
| UT-18 | `infer_qtype`-中文题型名识别 | 无 | `infer_qtype({"typename": "单选题"})` | `"single"` | P1 |
| UT-19 | `infer_qtype`-英文qtype直接返回 | 无 | `infer_qtype({"qtype": "multiple"})` | `"multiple"` | P1 |
| UT-20 | `infer_qtype`-无法识别返回空 | 无 | `infer_qtype({"typename": "未知题型"})` | `""` | P1 |
| UT-21 | `normalize_question`-单选题正常 | 无 | `{"qtype":"single","content_md":"测试题","examid":"001","options":[{"code":"A","content":"选项A","value":"1"},{"code":"B","content":"选项B","value":"0"}]}` | `(data, [])`，data含qtype/title/options，options中A的value="1" | P0 |
| UT-22 | `normalize_question`-单选题多正确答案报错 | 无 | `{"qtype":"single","content_md":"测试","examid":"001","options":[{"code":"A","content":"A","value":"1"},{"code":"B","content":"B","value":"1"}]}` | `(None, ["单选题必须恰好 1 个正确答案"])` | P0 |
| UT-23 | `normalize_question`-填空题无blanks报错 | 无 | `{"qtype":"fill","content_md":"测试____","examid":"001"}` | `(None, ["填空题需要 blanks 数组..."])` | P1 |
| UT-24 | `normalize_question`-问答题无答案且未启用AI判卷 | 无 | `{"qtype":"qa","content_md":"测试","examid":"001"}` | `(None, ["问答题需要 answer_md 参考答案..."])` | P1 |
| UT-25 | `normalize_question`-一题多问少于2个子题 | 无 | `{"qtype":"multi_part","content_md":"测试","examid":"001","sub_questions":[{"qtype":"single",...}]}` | `(None, ["一题多问需要 sub_questions 数组（至少 2 个小问）"])` | P1 |
| UT-26 | `duplicate_key`-相同内容相同key | 无 | `duplicate_key({"examid":"001","content_md":"**测试题**"})` 两次 | 两次返回值相同 | P1 |
| UT-27 | `duplicate_key`-Markdown格式不影响key | 无 | `duplicate_key({"examid":"001","content_md":"**测试**"})` vs `duplicate_key({"examid":"001","content_md":"测试"})` | 两个key相同（strip_markdown去格式后归一化） | P2 |
| UT-28 | `validate_markdown`-未闭合高亮标记 | 无 | `validate_markdown("这是一段==未闭合的高亮")` | `["存在未闭合的高亮标记 =="]` | P1 |
| UT-29 | `validate_markdown`-非法图片地址 | 无 | `validate_markdown("![img](javascript:alert(1))")` | `["图片地址不合法：javascript:alert(1)"]` | P1 |
| UT-30 | `strip_markdown`-去除所有标记 | 无 | `strip_markdown("**加粗** ==高亮== `代码`")` | `"加粗 高亮 代码"` | P2 |
| UT-31 | `AdminUser.set_password/check_password` | 无 | `user.set_password("test123"); user.check_password("test123")` | `True`；`user.check_password("wrong")` → `False` | P0 |
| UT-32 | `AdminUser.is_superuser`-超管角色 | Role(code='superadmin')存在 | `user.role = superadmin_role; user.is_superuser` | `True` | P1 |
| UT-33 | `AdminUser.permissions`-viewer角色 | Role(code='viewer')存在 | `user.role = viewer_role; user.permissions` | 不含`exam.manage`等manage权限，含`dashboard.view`等view权限 | P1 |
| UT-34 | `AdminToken.is_expired`-未过期 | 无 | 创建token，expires_at=now+1h | `token.is_expired` → `False` | P1 |
| UT-35 | `AdminToken.is_expired`-已过期 | 无 | 创建token，expires_at=now-1h | `token.is_expired` → `True` | P1 |
| UT-36 | `ImportJob.progress`-计算进度 | 无 | `job.total=100, job.succeeded=50, job.failed=10, job.skipped=5` | `job.progress` → `65`（round(65/100*100)） | P2 |
| UT-37 | `ImportJob.progress`-total为0时 | 无 | `job.total=0, job.status='pending'` | `job.progress` → `0` | P2 |
| UT-38 | `Role.clean_permissions`-过滤非法权限 | 无 | `role.permissions = ["dashboard.view", "invalid.perm", "exam.view"]` | `role.clean_permissions()` → `["dashboard.view", "exam.view"]` | P1 |
| UT-39 | `Document.to_client`-_id正确输出 | 存在doc_id="DOC001"的文档 | `doc.to_client()` | dict含`_id: "DOC001"`及其他data字段 | P1 |
| UT-40 | `Document.to_client`-无doc_id时用pk | doc_id=None | `doc.to_client()` | dict含`_id: str(doc.pk)` | P2 |
| UT-41 | `paginate`-分页结构正确 | 无 | `paginate([1,2,3], 100, 1, 20)` | `{"list":[1,2,3], "total":100, "page":1, "page_size":20, "total_pages":5}` | P1 |
| UT-42 | `parse_page`-非法值回退默认 | request.GET含page="abc" | `parse_page(request)` | `(1, 20)`（回退到默认值） | P2 |
| UT-43 | `parse_page`-page_size超过上限 | request.GET含page_size=999 | `parse_page(request, max_size=200)` | `(page, 200)`（被截断到max_size） | P2 |
| UT-44 | `_judge_options`-true值识别 | 无 | `_judge_options(True)` | `([{"code":"A","content":"正确","value":"1"}, {"code":"B","content":"错误","value":"0"}], None)` | P1 |
| UT-45 | `_judge_options`-无法识别的值 | 无 | `_judge_options("maybe")` | `(None, "判断题需要 answer 字段...")` | P1 |

### 3.4 测试方法

1. **Django TestCase**：使用`django.test.TestCase`配合SQLite内存数据库，每个测试方法自动回滚
2. **Fixture工厂**：使用`setUp`方法创建测试数据（角色、管理员、文档等）
3. **参数化测试**：对`to_text`/`to_number`/`parse_datetime`等函数使用多组输入验证
4. **Mock外部依赖**：AI调用（`_call_llm`）使用mock避免实际网络请求
5. **边界值分析**：空值、零值、最大值、特殊字符

### 3.5 预期结果

- 所有P0单元测试100%通过
- P1单元测试95%以上通过
- P2单元测试90%以上通过
- `as_obj` JSON字符串解析失败（UT-10）记录为已知缺陷
- 测试执行时间<30秒（SQLite内存模式）
- 输出可重复执行的`test_*.py`测试文件

---

## 四、集成测试

### 4.1 测试目标

验证多模块协同工作时的端到端业务流程，确保小程序端→后端→管理后台的数据流转一致性与接口契约对齐。

### 4.2 测试范围

| 流程 | 涉及模块 | 验证重点 |
|------|---------|---------|
| 用户答题全流程 | 小程序login→答题→交卷→管理后台查看记录 | openid传递、记录创建、管理端可见性 |
| 用户停用全流程 | 管理后台停用用户→小程序写入被拒→管理后台查看 | 状态联动、权限即时生效 |
| 题库管理全流程 | 管理后台导入题目→小程序查询题目→管理后台编辑 | 数据一致性、字段兼容 |
| 文章发布全流程 | 小程序提交文章→管理后台审核发布→小程序查看已发布文章 | 状态流转、审核联动 |
| AI配置全流程 | 管理后台配置AI→小程序AI辅助写作→管理后台查看配置 | 配置传递、脱敏一致性 |
| 管理员权限全流程 | 创建viewer角色管理员→登录→访问受限接口→403 | 权限隔离、错误响应 |
| 数据看板全流程 | 小程序产生答题数据→管理后台看板展示统计 | 统计准确性、数据聚合 |
| 用户画像全流程 | 小程序答题/错题→管理后台查看用户画像 | 画像数据完整性、排名计算 |

### 4.3 测试用例

| 用例ID | 描述 | 前置条件 | 输入（操作步骤） | 预期输出 | 优先级 |
|--------|------|---------|----------------|---------|--------|
| IT-01 | 用户答题全流程端到端 | 服务启动，存在科目和题库数据 | ①`POST /api/login/`获取openid ②`POST /api/collections/historys/`提交答题记录（含items/rightNum/createTime），Header带X-Openid ③`GET /api/admin/records/?_openid=<openid>`（管理端Token）查看记录 | ①返回openid ②返回_id ③管理端列表含该答题记录，_openid与openid一致，rightNum/createTime正确 | P0 |
| IT-02 | 用户停用联动验证 | 存在用户openid=test-disable-001，有答题记录 | ①管理端`PUT /api/admin/users/test-disable-001/`设status=disabled ②小程序端`POST /api/collections/historys/`带X-Openid=test-disable-001提交新记录 | ①返回成功 ②返回403，message含"账号已停用"——验证停用即时生效，小程序写入被拦截 | P0 |
| IT-03 | 题库导入到小程序查询全流程 | 管理端已登录，存在科目001001 | ①`POST /api/admin/questions/import/`导入2道单选题（examid=001001） ②`GET /api/collections/questions/?examid=001001`（小程序端）查询 ③管理端`GET /api/admin/questions/?examid=001001`查询 | ①导入成功succeeded=2 ②小程序端返回的data含导入的题目，_id一致 ③管理端返回的list含导入的题目，字段完整（qtype/title/options/examid） | P0 |
| IT-04 | 文章发布审核全流程 | 管理端已登录，小程序端有openid | ①小程序端`POST /api/collections/articles/`提交文章（标题+内容），带X-Openid ②管理端`GET /api/admin/articles/?status=pending`查看待审核 ③管理端`POST /api/admin/articles/<id>/audit/`审核通过（action=publish） ④小程序端`GET /api/collections/articles/`查询（不带status） | ①文章创建，status=pending（自动注入默认值） ②管理端列表含该文章 ③审核成功，status=published ④小程序端列表含该文章（因status=published被默认查询返回） | P0 |
| IT-05 | AI配置脱敏与小程序调用全流程 | 管理端已登录且有ai.config权限 | ①管理端`PUT /api/admin/ai/config/`设置apiKey=`sk-test123456`，enabled=true ②管理端`GET /api/admin/ai/config/`查看配置 ③小程序端`POST /api/ai/assist/`调用AI写作（prompt="测试"） | ①配置保存成功 ②返回的apiKey为`****3456`（脱敏） ③若LLM不可达返回50001错误；若可达返回content内容——验证配置从管理端到小程序端的传递链路 | P1 |
| IT-06 | viewer角色权限隔离端到端 | 存在viewer角色管理员账号 | ①viewer登录获取Token ②`GET /api/admin/dashboard/overview/`（有dashboard.view权限） ③`POST /api/admin/exams/`（缺少exam.manage权限） ④`DELETE /api/admin/users/<openid>/`（缺少超管权限） | ②返回200，数据正常 ③返回403，message含"无操作权限（缺少 exam.manage）" ④返回403，message含"删除用户数据仅超级管理员可执行" | P0 |
| IT-07 | 数据看板统计准确性验证 | 存在3个用户各5条答题记录 | ①`GET /api/admin/dashboard/overview/` ②`GET /api/admin/dashboard/ranking/` ③`GET /api/admin/dashboard/trend/?days=7` | ①totals.records=15，totals.users≥3 ②top_users按records降序排列，含3个用户 ③series长度=7，每天的数据与实际记录匹配 | P1 |
| IT-08 | 用户画像数据完整性验证 | 用户openid=test-profile-001，有3条答题记录和2条错题 | `GET /api/admin/users/test-profile-001/profile/` | 返回user/answer/exam/knowledge/weakness五个模块：answer.total_records=3，exam.total_exams=3，knowledge含科目维度掌握度，weakness含薄弱科目/题型统计 | P1 |
| IT-09 | 题目标签绑定与查询全流程 | 存在题目和标签数据 | ①`POST /api/admin/tags/`创建标签（knowledge类） ②`PUT /api/admin/questions/<id>/tags/`绑定标签 ③`GET /api/admin/questions/<id>/tags/`查看绑定 ④`GET /api/admin/tags/<tag_id>/`查看标签usage_count | ①标签创建成功 ②绑定成功，返回tag_ids ③返回已绑定的标签列表 ④标签usage_count增加——验证QuestionTag表与Document.tag_ids镜像同步 | P1 |
| IT-10 | 管理员修改密码后令牌失效验证 | 存在两个浏览器/会话同时登录同一管理员 | ①会话A`POST /api/admin/auth/password/`修改密码 ②会话B（旧Token）`GET /api/admin/auth/profile/` ③会话A（当前Token）`GET /api/admin/auth/profile/` | ①修改成功 ②返回401（旧Token已被清除） ③返回200（当前Token仍有效）——验证修改密码只清除其他端Token | P1 |
| IT-11 | Excel导入全流程验证 | 管理端已登录，存在科目001001 | ①`GET /api/admin/questions/import/templates/`获取模板列表 ②`GET /api/admin/questions/import/templates/single/`下载单选题模板 ③填写模板后`POST /api/admin/questions/import/excel/`上传 ④`GET /api/admin/questions/import/<job_id>/`查看导入结果 | ①返回5种题型模板 ②返回xlsx文件 ③返回导入任务结果（含succeeded/failed/skipped） ④返回任务详情与逐题结果 | P1 |
| IT-12 | 小程序错题本与管理端记录联动 | 用户有答题记录产生错题 | ①小程序端`POST /api/collections/notes/`添加错题（带_openid） ②管理端`GET /api/admin/notes/?_openid=<openid>`查看错题 ③管理端`GET /api/admin/notes/stats/`查看错题统计 ④管理端`GET /api/admin/users/<openid>/profile/`查看画像weakness模块 | ①错题创建成功 ②管理端列表含该错题 ③统计total增加 ④画像weakness.total_notes增加——验证错题数据从小程序到管理端的完整流转 | P1 |

### 4.4 测试方法

1. **API链式调用**：使用Python脚本按业务流程顺序调用多个API，前一步的输出作为后一步的输入
2. **数据一致性验证**：同一数据通过小程序端API和管理端API分别查询，比对字段一致性
3. **状态流转验证**：追踪文档status字段在多个操作间的变化路径
4. **权限端到端验证**：使用不同角色Token执行同一流程，验证权限隔离效果
5. **清理机制**：每个集成测试用例结束后清理创建的测试数据，保证可重复执行

### 4.5 预期结果

- P0集成测试100%通过（核心业务流程畅通）
- P1集成测试90%以上通过（管理功能流程正确）
- 小程序端与管理端数据流转无丢失、无字段不一致
- 权限隔离在端到端场景下有效
- 输出《集成测试结果报告》，含每个流程的步骤通过状态与数据比对结果

---

## 附录：测试环境与执行计划

### 测试环境准备

```bash
# 1. 启动后端服务
cd E:\workbuddy\考试宝\backend
python manage.py migrate
python manage.py init_admin          # 创建默认管理员admin/admin123
python manage.py seed_exam_data      # 导入演示数据
python manage.py runserver 0.0.0.0:8000

# 2. 启动管理后台（可选，用于前端联调）
cd E:\workbuddy\考试宝\web-admin
npm install && npm run dev

# 3. 执行单元测试
cd E:\workbuddy\考试宝\backend
python manage.py test
```

### 执行顺序

| 阶段 | 耗时预估 | 产出 |
|------|---------|------|
| 白盒测试 | 2小时 | 问题清单（含代码位置、严重程度、修复建议） |
| 黑盒测试 | 4小时 | API测试结果汇总（60个用例通过/失败状态） |
| 单元测试 | 3小时 | test_*.py文件 + 测试覆盖率报告 |
| 集成测试 | 3小时 | 端到端流程测试报告 |
| **总计** | **12小时** | **完整测试报告** |

### 缺陷分级标准

| 级别 | 定义 | 处理时限 |
|------|------|---------|
| P0 | 阻断核心功能 / 安全漏洞 | 立即修复 |
| P1 | 影响重要功能 / 数据不一致 | 发版前修复 |
| P2 | 影响边缘功能 / 体验问题 | 下个迭代修复 |
| P3 | 代码规范 / 已知限制 | 记录跟踪 |
