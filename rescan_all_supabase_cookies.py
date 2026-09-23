"""
Công cụ quét và làm sạch toàn bộ Cookie trên Supabase Database.
- Ưu tiên quét toàn bộ cookie đang có status='green' (kho đang phục vụ người dùng).
- Tự động phát hiện và xóa vĩnh viễn các tài khoản bị:
  + Lỗi thanh toán / nợ cước (Payment Hold, isUserOnHold: true, serviceEndReason: SERVICE_END_PAYMENT_FAILURE).
  + Hết hạn tài khoản (FORMER_MEMBER, NEVER_MEMBER).
  + Không xem được phim (canWatch: false).
  + Chuyển hướng sang trang cập nhật thẻ / đăng nhập lại.
- Cập nhật thời gian last_checked_at cho các cookie còn LIVE ngon lành.
"""

import sys
import io
import time
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# Windows terminal UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from checker import check_cookie, parse_cookie_line
from supabase_client import delete_cookie_by_id, update_cookie_check_result

SUPABASE_URL = "https://jvokfclberwizzeqmfnc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2b2tmY2xiZXJ3aXp6ZXFtZm5jIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODUwNjg4MSwiZXhwIjoyMTA0MDgyODgxfQ.jDbE_1Ee4c0Bi77sBj-gWZ4LwpcPyG6OS8YtiEzGR8I"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

WORKER_CONCURRENCY = 6
PAGE_SIZE = 100

def fetch_all_green_cookies():
    """Lấy danh sách toàn bộ cookie status='green'."""
    all_cookies = []
    offset = 0
    print("📥 Đang tải danh sách cookie status='green' từ Supabase...")
    while True:
        url = f"{SUPABASE_URL}/rest/v1/cookies?status=eq.green&select=id,raw_line,country_code,plan_name,email&order=id.asc&offset={offset}&limit={PAGE_SIZE}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            print(f"Lỗi tải trang offset={offset}: {resp.status_code}")
            break
        data = resp.json()
        if not data:
            break
        all_cookies.extend(data)
        offset += len(data)
        print(f"  Đã tải {len(all_cookies)} cookie...")
        if len(data) < PAGE_SIZE:
            break
    print(f"✅ Tổng cộng có {len(all_cookies)} cookie GREEN cần quét lại.\n")
    return all_cookies

stats_lock = threading.Lock()
stats = {
    "total": 0,
    "processed": 0,
    "live": 0,
    "hold_deleted": 0,
    "other_dead_deleted": 0,
    "error": 0,
}

def check_and_update(item):
    cid = item.get("id")
    raw = item.get("raw_line")
    cc = item.get("country_code", "??")
    
    if not raw or not cid:
        with stats_lock:
            stats["processed"] += 1
            stats["error"] += 1
        return
        
    nid, sid, extras = parse_cookie_line(raw)
    if not nid:
        delete_cookie_by_id(cid)
        with stats_lock:
            stats["processed"] += 1
            stats["other_dead_deleted"] += 1
        return

    # Kiểm tra cookie
    res = check_cookie(nid, sid, extra_cookies=extras, direct=True)
    status = res.get("status")
    
    with stats_lock:
        stats["processed"] += 1
        idx = stats["processed"]
        tot = stats["total"]
    
    if status == "LIVE":
        update_cookie_check_result(
            cookie_id=cid,
            status="green",
            fail_count=0,
            country_code=res.get("country") or cc,
            plan_name=res.get("plan"),
            email=res.get("email"),
        )
        with stats_lock:
            stats["live"] += 1
        print(f"[{idx}/{tot}] 🟢 LIVE: {cid[:8]}.. ({res.get('country', cc)}) - {res.get('plan', '-')}")
        
    elif status == "DEAD":
        reason = res.get("dead_reason", "DEAD")
        is_hold = "Hold" in reason or "Payment" in reason or "isUserOnHold" in reason
        
        # Xóa ngay khỏi Supabase
        delete_cookie_by_id(cid)
        
        with stats_lock:
            if is_hold:
                stats["hold_deleted"] += 1
            else:
                stats["other_dead_deleted"] += 1
                
        tag = "🔴 [PAYMENT HOLD - ĐÃ XÓA]" if is_hold else "🗑️ [DEAD - ĐÃ XÓA]"
        print(f"[{idx}/{tot}] {tag} {cid[:8]}.. - Lý do: {reason}")
        
    else:
        err = res.get("error", "Unknown error")
        with stats_lock:
            stats["error"] += 1
        print(f"[{idx}/{tot}] ⚠️ LỖI MẠNG ({err}): {cid[:8]}..")

def main():
    cookies = fetch_all_green_cookies()
    if not cookies:
        print("Không có cookie nào cần quét.")
        return

    stats["total"] = len(cookies)
    start_time = time.time()
    
    print(f"🚀 Bắt đầu quét với {WORKER_CONCURRENCY} luồng song song...")
    print("=" * 70)
    
    with ThreadPoolExecutor(max_workers=WORKER_CONCURRENCY) as executor:
        futures = [executor.submit(check_and_update, c) for c in cookies]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                pass
                
    elapsed = time.time() - start_time
    print("=" * 70)
    print("🎉 HOÀN TẤT QUÉT TOÀN BỘ KHO COOKIE SUPABASE!")
    print(f"⏱️ Thời gian: {elapsed:.1f} giây")
    print(f"📊 Tổng kiểm tra: {stats['processed']}/{stats['total']}")
    print(f"🟢 Còn sống (LIVE hợp lệ): {stats['live']}")
    print(f"🛑 Bị nợ cước / Payment Hold (Đã dọn sạch): {stats['hold_deleted']}")
    print(f"🗑️ Chết vì lý do khác (Đã dọn sạch): {stats['other_dead_deleted']}")
    print(f"⚠️ Lỗi tạm thời (giữ lại kiểm tra sau): {stats['error']}")
    print("=" * 70)

if __name__ == "__main__":
    main()
