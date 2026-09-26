"""End-to-end API test for exams, notes (stats), and studynotes modules."""
import json
import urllib.request
import urllib.error
import urllib.parse

BASE = "http://127.0.0.1:8000/api/admin"

# 1. Login
login_data = json.dumps({"username": "admin", "password": "admin123"}).encode()
req = urllib.request.Request(f"{BASE}/auth/login/", data=login_data, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req)
result = json.loads(resp.read())
TOKEN = result["data"]["token"]
print(f"[LOGIN] code={result['code']} token={TOKEN[:16]}...")

headers = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}

def api_call(method, path, body=None):
    # URL-encode query string portion for non-ASCII chars
    if '?' in path:
        base, query = path.split('?', 1)
        path = base + '?' + urllib.parse.urlencode(urllib.parse.parse_qsl(query))
    url = f"{BASE}/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

# ============ EXAMS MODULE ============
print("\n=== EXAMS MODULE ===")

# Create exam with full config
exam_body = {
    "_id": "EXAM_TEST_001",
    "name": "测试考试-软件设计师",
    "code": "TEST001",
    "desc": "用于测试的考试",
    "status": "draft",
    "duration": 120,
    "questionCount": 50,
    "totalScore": 100,
    "passScore": 60,
    "scoringType": "auto",
}
res = api_call("POST", "exams/", exam_body)
print(f"[CREATE EXAM] code={res.get('code')} msg={res.get('message')} id={res.get('data', {}).get('_id')}")

# List with status filter
res = api_call("GET", "exams/?status=draft")
data = res.get("data", {})
print(f"[LIST EXAMS status=draft] code={res.get('code')} total={data.get('total')} items={len(data.get('list', []))}")

# Detail
res = api_call("GET", "exams/EXAM_TEST_001/")
doc = res.get("data", {})
print(f"[DETAIL EXAM] code={res.get('code')} name={doc.get('name')} status={doc.get('status')} duration={doc.get('duration')} passScore={doc.get('passScore')} scoringType={doc.get('scoringType')}")

# Update exam
res = api_call("PUT", "exams/EXAM_TEST_001/", {
    "name": "测试考试-已更新", "code": "TEST001", "desc": "更新后的说明",
    "status": "published", "duration": 90, "questionCount": 40,
    "totalScore": 100, "passScore": 70, "scoringType": "hybrid",
})
print(f"[UPDATE EXAM] code={res.get('code')} msg={res.get('message')}")

# Verify update
res = api_call("GET", "exams/EXAM_TEST_001/")
doc = res.get("data", {})
print(f"[VERIFY EXAM] name={doc.get('name')} status={doc.get('status')} duration={doc.get('duration')} passScore={doc.get('passScore')}")

# Validation test: passScore > totalScore should fail
res = api_call("PUT", "exams/EXAM_TEST_001/", {
    "name": "测试考试", "totalScore": 50, "passScore": 80,
})
print(f"[VALIDATION passScore>totalScore] code={res.get('code')} (expect non-zero) msg={res.get('message')}")

# Delete exam
res = api_call("DELETE", "exams/EXAM_TEST_001/")
print(f"[DELETE EXAM] code={res.get('code')} msg={res.get('message')}")

# ============ NOTES STATS MODULE ============
print("\n=== NOTES STATS MODULE ===")

# Get notes stats
res = api_call("GET", "notes/stats/")
data = res.get("data", {})
print(f"[NOTES STATS] code={res.get('code')} total={data.get('total')}")
print(f"  by_review_status={data.get('by_review_status', {})}")
print(f"  by_category count={len(data.get('by_category', {}))}")
print(f"  frequent top={len(data.get('frequent', []))}")

# List notes with reviewStatus filter
res = api_call("GET", "notes/?reviewStatus=pending")
data = res.get("data", {})
print(f"[LIST NOTES reviewStatus=pending] code={res.get('code')} total={data.get('total')}")

# ============ STUDYNOTES MODULE ============
print("\n=== STUDYNOTES MODULE ===")

# Create study note
sn_body = {
    "_id": "SN_TEST_001",
    "title": "测试笔记-数据结构重点",
    "category": "数据结构",
    "tags": "重点,必考,易错",
    "summary": "数据结构核心知识点总结",
    "content": "# 栈和队列\n\n栈：后进先出LIFO\n队列：先进先出FIFO\n\n# 树\n\n二叉树遍历：前序、中序、后序",
}
res = api_call("POST", "studynotes/", sn_body)
print(f"[CREATE STUDYNOTE] code={res.get('code')} msg={res.get('message')} id={res.get('data', {}).get('_id')}")

# List with category filter
res = api_call("GET", "studynotes/?category=数据结构")
data = res.get("data", {})
print(f"[LIST STUDYNOTES category=数据结构] code={res.get('code')} total={data.get('total')}")

# Detail
res = api_call("GET", "studynotes/SN_TEST_001/")
doc = res.get("data", {})
print(f"[DETAIL STUDYNOTE] code={res.get('code')} title={doc.get('title')} category={doc.get('category')} tags={doc.get('tags')}")

# Update
res = api_call("PUT", "studynotes/SN_TEST_001/", {
    "title": "测试笔记-已更新", "category": "软件工程", "tags": "更新,测试",
    "summary": "更新后的摘要", "content": "更新后的内容",
})
print(f"[UPDATE STUDYNOTE] code={res.get('code')} msg={res.get('message')}")

# Verify
res = api_call("GET", "studynotes/SN_TEST_001/")
doc = res.get("data", {})
print(f"[VERIFY STUDYNOTE] title={doc.get('title')} category={doc.get('category')}")

# Validation: empty title should fail
res = api_call("POST", "studynotes/", {"title": "", "category": "test"})
print(f"[VALIDATION empty title] code={res.get('code')} (expect non-zero) msg={res.get('message')}")

# Delete
res = api_call("DELETE", "studynotes/SN_TEST_001/")
print(f"[DELETE STUDYNOTE] code={res.get('code')} msg={res.get('message')}")

# Verify deletion
res = api_call("GET", "studynotes/SN_TEST_001/")
print(f"[VERIFY DELETE] code={res.get('code')} (expect non-zero)")

# ============ PERMISSIONS CHECK ============
print("\n=== PERMISSIONS CHECK ===")
res = api_call("GET", "auth/permissions/")
data = res.get("data", [])
studynote_perms = [p for g in data for p in g.get("items", []) if "studynote" in p.get("code", "")]
print(f"[PERMISSIONS] studynote perms found: {len(studynote_perms)}")
for p in studynote_perms:
    print(f"  {p['code']}: {p['name']}")

print("\n=== ALL TESTS COMPLETE ===")
