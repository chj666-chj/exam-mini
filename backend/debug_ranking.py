"""Debug script: check user data distribution between profiles and historys."""
import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
django.setup()
from core.models import Document
from collections import Counter

# profiles
profiles = Document.objects.filter(collection='profiles')
print('=== profiles 集合 ===')
print('总文档数:', profiles.count())
profile_openids = set()
for p in profiles:
    oid = p.data.get('_openid', '')
    nick = (p.data.get('userInfo', {}) or {}).get('nickName', '?')
    print('  doc_id=%s  _openid=%s  nick=%s' % (p.doc_id, oid, nick))
    if oid:
        profile_openids.add(oid)

# historys
print()
print('=== historys 集合 ===')
historys = Document.objects.filter(collection='historys')
print('总文档数:', historys.count())
hist_openids = Counter()
for h in historys:
    oid = h.data.get('_openid', '')
    if oid:
        hist_openids[oid] += 1
print('不同用户数:', len(hist_openids))
for oid, cnt in hist_openids.most_common():
    print('  _openid=%s  记录数=%d' % (oid, cnt))

# diff
print()
print('=== 差异分析 ===')
only_profiles = profile_openids - set(hist_openids.keys())
only_historys = set(hist_openids.keys()) - profile_openids
both = profile_openids & set(hist_openids.keys())
print('仅在 profiles（有档案无答题记录）:', len(only_profiles))
for oid in only_profiles:
    p = profiles.filter(data___openid=oid).first()
    nick = (p.data.get('userInfo', {}) or {}).get('nickName', '?') if p else '?'
    print('  %s  nick=%s' % (oid, nick))
print('仅在 historys（有答题无档案）:', len(only_historys))
for oid in only_historys:
    print('  %s' % oid)
print('两者都有:', len(both))

# check login default
print()
print('=== login 默认 openid ===')
from django.conf import settings
print('DEV_DEFAULT_OPENID:', getattr(settings, 'DEV_DEFAULT_OPENID', 'N/A'))
