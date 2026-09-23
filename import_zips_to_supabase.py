"""
Nạp trực tiếp toàn bộ cookie hợp lệ từ 2 file zip vào Supabase Database:
- d:\\Cuồng Netflix\\Netflix.zip
- d:\\Cuồng Netflix\\Netflix @hydrax001.zip
"""

import sys
import io
import zipfile
import re
import datetime
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SUPABASE_URL = "https://jvokfclberwizzeqmfnc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2b2tmY2xiZXJ3aXp6ZXFtZm5jIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODUwNjg4MSwiZXhwIjoyMTA0MDgyODgxfQ.jDbE_1Ee4c0Bi77sBj-gWZ4LwpcPyG6OS8YtiEzGR8I"

headers = {
    "Content-Type": "application/json",
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Prefer": "resolution=ignore-duplicates,return=representation",
}

SAFE_COOKIE_LEN = 2500
BATCH_SIZE = 100

def parse_cookie_file(content, filename):
    # 1. Check hold / 0 payments
    if re.search(r'\[0\s*payments?\]', content, re.I) or re.search(r'payments?:\s*0\b', content, re.I):
        return None
    if (
        re.search(r'hold status:\s*yes|membership\s*hold|payment\s*hold|isUserOnHold\s*:\s*true', content, re.I)
        or re.search(r'serviceEndReason\s*:\s*"?SERVICE_END_PAYMENT', content, re.I)
    ):
        return None

    # 2. Extract country
    cc = "UN"
    m_cc = re.search(r'[–-•*]?\s*Country:\s*([A-Za-z]{2})', content) or re.search(r'\[([A-Za-z]{2})\]', filename)
    if m_cc:
        cc = m_cc.group(1).upper()

    # 3. Extract plan
    plan = "Basic"
    m_p = re.search(r'[–-•*]?\s*Plan:\s*([^\r\n]+)', content) or re.search(r'\[([A-Za-z0-9 ]+)\]', filename)
    if m_p:
        plan = m_p.group(1).strip()
    if plan.lower() in ("unknown", "none", "cancelled"):
        return None

    # 4. Extract email
    email = None
    m_e = re.search(r'[–-•*]?\s*Email:\s*([^\s\r\n]+)', content) or re.search(r'[\w.-]+@[\w.-]+\.[a-zA-Z]{2,}', content)
    if m_e:
        email = (m_e.group(1) if m_e.groups() else m_e.group(0)).strip()

    # 5. Extract Netscape lines
    lines = content.split('\n')
    netscape_lines = []
    has_netflix_id = False
    for l in lines:
        line_clean = l.strip()
        if line_clean.startswith('.netflix.com') or '\tNetflixId\t' in line_clean or '\tSecureNetflixId\t' in line_clean:
            if '\tNetflixId\t' in line_clean or line_clean.endswith('NetflixId'):
                has_netflix_id = True
            netscape_lines.append(line_clean)

    if not has_netflix_id:
        # Check raw NetflixId=
        m_nid = re.search(r'NetflixId[=\s:]+([^\s;\r\n]+)', content)
        if m_nid:
            has_netflix_id = True
            cookie_str = f"NetflixId={m_nid.group(1)}"
            m_sec = re.search(r'SecureNetflixId[=\s:]+([^\s;\r\n]+)', content)
            if m_sec:
                cookie_str += f"; SecureNetflixId={m_sec.group(1)}"
            raw_line = cookie_str
        else:
            return None
    else:
        raw_line = '\n'.join(netscape_lines)

    if not raw_line or len(raw_line) < 30:
        return None

    final_raw = raw_line[:SAFE_COOKIE_LEN]
    return {
        "raw_line": final_raw,
        "country_code": cc,
        "plan_name": plan,
        "email": email,
        "status": "unknown",  # Import với unknown để worker kiểm tra hoặc dùng ngay
        "website_name": "Netflix",
    }

def import_zip(zip_path):
    print(f"\n📂 Đang xử lý file: {zip_path}")
    items = []
    seen_raw = set()
    with zipfile.ZipFile(zip_path, 'r') as z:
        txt_files = [n for n in z.namelist() if n.endswith('.txt') and not n.startswith('__MACOSX')]
        print(f"  Tổng file .txt: {len(txt_files)}")
        for f in txt_files:
            try:
                content = z.read(f).decode('utf-8', errors='ignore')
                item = parse_cookie_file(content, f)
                if item:
                    if item["raw_line"] not in seen_raw:
                        seen_raw.add(item["raw_line"])
                        items.append(item)
            except Exception:
                pass

    print(f"  Số cookie hợp lệ lọc được (đã loại bỏ 0-payments & hold): {len(items)}")
    
    total_added = 0
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i:i + BATCH_SIZE]
        payload = [
            {
                **b,
                "created_at": now,
                "updated_at": now,
                "last_checked_at": None,
            }
            for b in batch
        ]
        url = f"{SUPABASE_URL}/rest/v1/cookies?on_conflict=raw_line"
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            if r.status_code in (200, 201):
                data = r.json()
                if isinstance(data, list):
                    total_added += len(data)
            else:
                print(f"  Batch {i//BATCH_SIZE + 1} lỗi HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"  Batch {i//BATCH_SIZE + 1} exception: {e}")

    print(f"  ✅ ĐÃ NẠP THÀNH CÔNG: {total_added} cookie mới vào Supabase!")
    print(f"  ℹ️ Bỏ qua {len(items) - total_added} cookie đã tồn tại trước đó.")
    return total_added

def main():
    print("🚀 Bắt đầu quá trình nạp cookie từ 2 file zip...")
    c1 = import_zip(r"d:\Cuồng Netflix\Netflix @hydrax001.zip")
    c2 = import_zip(r"d:\Cuồng Netflix\Netflix.zip")
    print("\n" + "=" * 60)
    print(f"🎉 TỔNG KẾT: Đã nạp thành công tổng cộng {c1 + c2} cookie Netflix vào Supabase Database!")
    print("=" * 60)

if __name__ == "__main__":
    main()
