import requests
import re
import json
from curl_cffi import requests as curl_requests
from checker import parse_cookie_line

SUPABASE_URL = "https://jvokfclberwizzeqmfnc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2b2tmY2xiZXJ3aXp6ZXFtZm5jIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODUwNjg4MSwiZXhwIjoyMTA0MDgyODgxfQ.jDbE_1Ee4c0Bi77sBj-gWZ4LwpcPyG6OS8YtiEzGR8I"

headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
r = requests.get(f"{SUPABASE_URL}/rest/v1/cookies?id=eq.2e94394e-7305-42d6-99c5-afc30ed193f6&select=raw_line", headers=headers)
raw = r.json()[0]["raw_line"]
nid, sid, extras = parse_cookie_line(raw)
print("nid:", nid[:20] if nid else None)

session = curl_requests.Session(impersonate="chrome120")
cookies = {"NetflixId": nid}
if sid:
    cookies["SecureNetflixId"] = sid
resp = session.get("https://www.netflix.com/YourAccount", cookies=cookies, timeout=20)
text = resp.text

print("Status:", resp.status_code, "URL:", resp.url)

for m in re.finditer(r'"([^"]*hold[^"]*)"\s*:\s*([^,}\]]+)', text, re.I):
    print(f"Hold key: {m.group(1)} -> {m.group(2)[:80]}")

gh = re.search(r'"growthHoldMetadata":\{([^}]+)\}', text)
if gh:
    print("growthHoldMetadata:", gh.group(0))

gh_feature = re.search(r'"growthFeatureOnlyHoldMetadata":\{([^}]+)\}', text)
if gh_feature:
    print("growthFeatureOnlyHoldMetadata:", gh_feature.group(0))
