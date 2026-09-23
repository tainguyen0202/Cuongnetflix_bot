import json
import requests
from checker import IOS_ESN, parse_cookie_line

SUPABASE_URL = "https://jvokfclberwizzeqmfnc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2b2tmY2xiZXJ3aXp6ZXFtZm5jIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODUwNjg4MSwiZXhwIjoyMTA0MDgyODgxfQ.jDbE_1Ee4c0Bi77sBj-gWZ4LwpcPyG6OS8YtiEzGR8I"

headers_db = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
r = requests.get(f"{SUPABASE_URL}/rest/v1/cookies?id=eq.2e94394e-7305-42d6-99c5-afc30ed193f6&select=raw_line", headers=headers_db)
raw = r.json()[0]["raw_line"]
nid, sid, extras = parse_cookie_line(raw)

headers = {
    "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
    "Cookie": f"NetflixId={nid}",
}

# Test multiple paths in iOS Argo API
# For example: ["account", "canWatch"], ["account", "isOnHold"], ["account", "membershipStatus"]
for p in ['["account","token","default"]', '["account",["canWatch","isOnHold","isUserOnHold","membershipStatus","hasValidPaymentMethod"]]', '["userInfo",["canWatch","isOnHold","membershipStatus"]]']:
    params = {
        "appVersion": "15.48.1",
        "device_type": "NFAPPL-02-",
        "esn": IOS_ESN.replace("=", "%3D"),
        "path": p,
        "pathFormat": "graph",
        "responseFormat": "json",
    }
    res = requests.get("https://ios.prod.ftl.netflix.com/iosui/user/15.48", headers=headers, params=params, timeout=10)
    print(f"Path {p}: status={res.status_code}")
    print(res.text[:300])
