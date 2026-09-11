# Deploy Bot Mới lên JustRunMy.App

## 1. Chuẩn bị Zip

```bash
cd /root/web-bot-cuongnetflix/netflix-bot-new
# Zip toàn bộ code bot (KHÔNG gồm .env — env vars set trên hosting)
zip -r bot.zip config.py supabase_client.py handlers.py api_server.py main.py checker.py proxies.py shrinkme.py PROXY_URLS.txt requirements.txt Dockerfile
```

## 2. Deploy lên JustRunMy.App

1. Vào https://justrunmy.app → Đăng ký/Đăng nhập
2. Chọn **Zip Upload**
3. Upload `bot.zip`
4. Chọn **Python** runtime
5. Set **Start Command**: `python3 -u main.py`
6. Set **Port**: `8081` (API server cho web gọi check-cookie)
7. Set **Environment Variables**:
   - `BOT_TOKEN` = `8493032763:AAH9931Ol39hYM5roC6s48BlNxsNrdH4TQM`
   - `BOT_USERNAME` = `@cuongnetflix_bot`
   - `SUPABASE_URL` = `https://jvokfclberwizzeqmfnc.supabase.co`
   - `SUPABASE_SERVICE_KEY` = (lấy từ .env)
   - `SHRINKME_API_KEY` = (lấy từ .env)
   - `ADMIN_IDS` = `1208795685`
   - `WEB_URL` = `https://cuongnetflix-web.vercel.app`
8. **Start** app

## 3. Lấy URL API bot

Sau khi deploy, JustRunMy.App cấp URL công khai (vd: `https://xxx.justrunmy.app`).
Port 8081 sẽ được map thành URL đó.

## 4. Cập nhật web (Vercel)

1. Mở `api/check-cookie.ts` và `api/batch-check.ts`
2. Đổi `BOT_API_URL` từ `http://103.195.5.183:8081` sang URL bot mới
3. Thêm env var `SUPABASE_SERVICE_KEY` vào Vercel (nếu chưa có)
4. Redeploy web

## 5. Test

1. Mở bot Telegram `@cuongnetflix_bot` → `/start`
2. Đăng nhập web → Hồ sơ → bấm **Liên kết Telegram** → mở bot → gõ `/start`
   (liên kết tự động, không cần nhập ID thủ công)
3. Dùng `/loginlink` trên bot
4. Test web check cookie (NetflixProcessorTool)
