"""
Quét một lượt pool cookie status='unknown' trên Supabase
để tìm các cookie LIVE chuẩn xác, đẩy vào status='green'.
Đồng thời xóa các cookie DEAD / Payment Hold khỏi DB.
"""

import sys
import io
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from checker import check_cookie, parse_cookie_line
from supabase_client import delete_cookie_by_id, update_cookie_check_result

SUPABASE_URL = "https://jvokfclberwizzeqmfnc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2b2tmY2xiZXJ3aXp6ZXFtZm5jIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODUwNjg4MSwiZXhwIjoyMTA0MDgyODgxfQ.jDbE_1Ee4c0Bi77sBj-gWZ4LwpcPyG6OS8YtiEzGR8I"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

BATCH_LIMIT = 500
CONCURRENCY = 6

def get_unknown_batch(limit=BATCH_LIMIT):
    url = f"{SUPABASE_URL}/rest/v1/cookies?status=eq.unknown&select=id,raw_line&order=id.asc&limit={limit}"
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return r.json()
    return []

def process_item(item):
    cid = item.get("id")
    raw = item.get("raw_line")
    if not cid or not raw:
        return "error"
    nid, sid, extras = parse_cookie_line(raw)
    if not nid:
        delete_cookie_by_id(cid)
        return "deleted"
    res = check_cookie(nid, sid, extra_cookies=extras, direct=True)
    st = res.get("status")
    if st == "LIVE":
        update_cookie_check_result(
            cookie_id=cid,
            status="green",
            fail_count=0,
            country_code=res.get("country"),
            plan_name=res.get("plan"),
            email=res.get("email"),
        )
        print(f"🟢 [LIVE TÌM THẤY] {cid[:8]}.. ({res.get('country')}) - {res.get('plan')}")
        return "live"
    elif st == "DEAD":
        delete_cookie_by_id(cid)
        return "dead"
    return "error"

def main():
    print(f"📥 Đang lấy {BATCH_LIMIT} cookie từ kho unknown...")
    items = get_unknown_batch(BATCH_LIMIT)
    if not items:
        print("Không có cookie unknown nào.")
        return
    print(f"🚀 Bắt đầu quét {len(items)} cookie...")
    stats = {"live": 0, "dead": 0, "error": 0, "deleted": 0}
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = [executor.submit(process_item, it) for it in items]
        for f in as_completed(futures):
            res = f.result()
            if res in stats:
                stats[res] += 1
    print("=" * 60)
    print(f"Kết quả quét đợt này: LIVE={stats['live']}, DEAD đã xóa={stats['dead'] + stats['deleted']}, Lỗi mạng={stats['error']}")

if __name__ == "__main__":
    main()
