"""Quick API test: verify TOC field CRUD through the knowledge endpoint."""
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000/api/admin"
TOKEN = None

# 1. Login to get token
login_data = json.dumps({"username": "admin", "password": "admin123"}).encode()
req = urllib.request.Request(f"{BASE}/auth/login/", data=login_data, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req)
result = json.loads(resp.read())
TOKEN = result["data"]["token"]
print(f"[LOGIN] token={TOKEN[:16]}...")

headers = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}

def api_call(method, path, body=None):
    url = f"{BASE}/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

# 2. Create a document with TOC
toc_data = [
    {"title": "1.1 测试章节", "page": 1, "level": 1, "children": [
        {"title": "1.1.1 子节A", "page": 2, "level": 2, "children": [
            {"title": "1.1.1.1 三级条目", "page": 3, "level": 3}
        ]},
        {"title": "1.1.2 子节B", "page": 5, "level": 2}
    ]},
    {"title": "1.2 第二章节", "page": 10, "level": 1}
]

create_body = {
    "_id": "KB_TOC_TEST_001",
    "title": "TOC测试文档",
    "type": "textbook",
    "category": "测试分类",
    "summary": "用于测试TOC目录编辑功能",
    "content": "# 测试内容",
    "pages": 20,
    "sortWeight": 50,
    "bookId": "BK_TEST",
    "bookTitle": "测试书籍",
    "chapterNo": 1,
    "chapterTitle": "测试章节",
    "toc": toc_data,
}

res = api_call("POST", "knowledge/", create_body)
print(f"[CREATE] code={res.get('code')} msg={res.get('message')} id={res.get('data', {}).get('_id')}")

# 3. Retrieve and verify TOC
res = api_call("GET", "knowledge/KB_TOC_TEST_001/")
doc = res.get("data", {})
toc = doc.get("toc", [])
print(f"[DETAIL] code={res.get('code')} title={doc.get('title')} toc_entries={len(toc)}")
print(f"  L1[0]: title={toc[0]['title']} page={toc[0]['page']} level={toc[0]['level']}")
print(f"  L1[0].children: {len(toc[0].get('children', []))} entries")
if toc[0].get("children"):
    c = toc[0]["children"][0]
    print(f"  L2[0]: title={c['title']} page={c['page']} level={c['level']}")
    if c.get("children"):
        gc = c["children"][0]
        print(f"  L3[0]: title={gc['title']} page={gc['page']} level={gc['level']}")
print(f"  L1[1]: title={toc[1]['title']} page={toc[1]['page']} level={toc[1]['level']}")

# 4. Update TOC (add entry, remove a child)
updated_toc = json.loads(json.dumps(toc))  # deep clone
updated_toc.append({"title": "1.3 新增章节", "page": 15, "level": 1, "children": []})
updated_toc[0]["children"].pop()  # remove last child of first entry

update_body = {
    "title": doc["title"],
    "type": doc["type"],
    "category": doc.get("category", ""),
    "summary": doc.get("summary", ""),
    "content": doc.get("content", ""),
    "pages": doc.get("pages", 0),
    "sortWeight": doc.get("sortWeight", 0),
    "bookId": doc.get("bookId", ""),
    "bookTitle": doc.get("bookTitle", ""),
    "chapterNo": doc.get("chapterNo", 0),
    "chapterTitle": doc.get("chapterTitle", ""),
    "toc": updated_toc,
}

res = api_call("PUT", "knowledge/KB_TOC_TEST_001/", update_body)
print(f"[UPDATE] code={res.get('code')} msg={res.get('message')}")

# 5. Verify update
res = api_call("GET", "knowledge/KB_TOC_TEST_001/")
doc = res.get("data", {})
toc = doc.get("toc", [])
print(f"[VERIFY] toc_entries={len(toc)} (expect 3)")
print(f"  L1[0].children: {len(toc[0].get('children', []))} (expect 1, was 2)")
print(f"  L1[2]: title={toc[2]['title']} (expect '1.3 新增章节')")

# 6. Test empty TOC
update_body["toc"] = []
res = api_call("PUT", "knowledge/KB_TOC_TEST_001/", update_body)
print(f"[UPDATE empty TOC] code={res.get('code')} msg={res.get('message')}")
res = api_call("GET", "knowledge/KB_TOC_TEST_001/")
doc = res.get("data", {})
print(f"[VERIFY empty] toc={doc.get('toc', 'MISSING')} (expect [])")

# 7. Cleanup - delete test doc
res = api_call("DELETE", "knowledge/KB_TOC_TEST_001/")
print(f"[DELETE] code={res.get('code')} msg={res.get('message')}")

# 8. Verify deletion
res = api_call("GET", "knowledge/KB_TOC_TEST_001/")
print(f"[VERIFY DELETE] code={res.get('code')} (expect non-zero / error)")

print("\n=== TOC API tests complete ===")
