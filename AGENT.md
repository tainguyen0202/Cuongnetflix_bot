# AGENT.md — CuongNetflix Bot (Python Telegram + Supabase)

> Đọc file này TRƯỚC khi sửa code bot. Web: `Web-cuongnetflix/AGENT.md`.

## Project / System Objective
Bot Telegram `@cuongnetflix_bot` tạo link đăng nhập Netflix từ pool cookie. Supabase là
source of truth (cookie pool + profile/quota). Bot là worker mỏng: check cookie, gen
NFToken + 3 device links, phục vụ web API (check-cookie/batch-check). Deploy lên
JustRunMy.App (Python runtime, port 8081).

## Current Status
- Bot mới (thay thế `netflix-bot-tele` cũ đã xóa — bot cũ dùng file cục bộ, không Supabase).
- Cookie pool load từ Supabase `cookies` table (website_name='Netflix', status != 'dead').
- Quota/plan đọc-ghi trực tiếp trên `profiles` table (web quản lý plan qua SePay webhook).
- Chỉ có `/start`, `/loginlink`, `/lang`. Gate shrinkme chỉ cho user free.
- Liên kết web <-> bot TỰ ĐỘNG: web tạo token trong `telegram_links` → user bấm deep link
  `t.me/bot?start=link_XXXX` → bot `/start link_XXXX` ghi `telegram_id` vào profile + đánh
  dấu token linked. Không còn nhập ID thủ công.

## Current Architecture
```
main.py               — entry: load cookie pool, setup commands, start API server, polling
config.py             — env config (BOT_TOKEN, SUPABASE_URL, WEB_URL, ADMIN_IDS...)
supabase_client.py    — Supabase client: cookie pool + profile/quota + telegram_links CRUD
handlers.py           — /start (gồm link_XXXX + shrinkme_), /loginlink, /lang
checker.py            — check cookie, generate/validate NFToken
api_server.py         — HTTP API cho web (check-cookie, batch-check, combo-check) port 8081
shrinkme.py           — rút gọn link gate (chỉ free user)
lang.py               — i18n vi/en
proxies.py            — proxy pool
```

## Key Technical Decisions
- Supabase service_role key = full access (bot backend). Web dùng anon/authenticated.
- Quota: free → 0 (phải qua gate shrinkme); basic/pro → quota_limit/ngày, reset theo giờ VN.
- Plan hết hạn 30 ngày → tự downgrade free khi dùng /loginlink.
- Telegram link: token single-use, TTL 10 phút, bind web_user_id; bot ghi telegram_id
  bằng service_role (không cần gọi API web).
- Rate limit /loginlink: 5 lần/15 phút/user.

## Env (set trên JustRunMy.App)
- `BOT_TOKEN`, `BOT_USERNAME`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- `SHRINKME_API_KEY`, `ADMIN_IDS`, `WEB_URL`

## Testing
- `python3 -c "import ast; ast.parse(open('handlers.py').read())"` (syntax check).
- Test thật: mở bot → /start → /loginlink; web → Hồ sơ → Liên kết Telegram.

## Non-Goals
- Không lưu secret trong code (dùng .env / env hosting).
- Không quản lý plan trực tiếp (web + SePay webhook lo phần đó).
