import json
from checker import generate_nftoken, parse_cookie_line
import requests

SUPABASE_URL = "https://jvokfclberwizzeqmfnc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2b2tmY2xiZXJ3aXp6ZXFtZm5jIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODUwNjg4MSwiZXhwIjoyMTA0MDgyODgxfQ.jDbE_1Ee4c0Bi77sBj-gWZ4LwpcPyG6OS8YtiEzGR8I"

headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
r = requests.get(f"{SUPABASE_URL}/rest/v1/cookies?id=eq.2e94394e-7305-42d6-99c5-afc30ed193f6&select=raw_line", headers=headers)
raw = r.json()[0]["raw_line"]
nid, sid, extras = parse_cookie_line(raw)

token, err = generate_nftoken({"NetflixId": nid})
print("Token generated:", token[:30] if token else None, "Error:", err)
