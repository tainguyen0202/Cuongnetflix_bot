import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import requests
from checker import check_cookie, parse_cookie_line

SUPABASE_URL = "https://jvokfclberwizzeqmfnc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2b2tmY2xiZXJ3aXp6ZXFtZm5jIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODUwNjg4MSwiZXhwIjoyMTA0MDgyODgxfQ.jDbE_1Ee4c0Bi77sBj-gWZ4LwpcPyG6OS8YtiEzGR8I"

headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

for cid in ["2e94394e-7305-42d6-99c5-afc30ed193f6", "2151af06-e97c-4ae7-aa76-a64bbf8ca838"]:
    r = requests.get(f"{SUPABASE_URL}/rest/v1/cookies?id=eq.{cid}&select=raw_line", headers=headers)
    raw = r.json()[0]["raw_line"]
    nid, sid, extras = parse_cookie_line(raw)
    res = check_cookie(nid, sid, extras, direct=True)
    print(f"[{cid}] status={res.get('status')}, reason={res.get('dead_reason')}, hard_dead={res.get('is_hard_dead')}")
