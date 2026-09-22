-- Migration: Thêm strike system cho bảng cookies để check live/die an toàn
-- Chạy đoạn SQL này trên Supabase Dashboard -> SQL Editor

ALTER TABLE cookies ADD COLUMN IF NOT EXISTS check_fail_count integer DEFAULT 0;
ALTER TABLE cookies ADD COLUMN IF NOT EXISTS last_check_error text;

-- Index hỗ trợ query batch check nhanh theo thứ tự ưu tiên
CREATE INDEX IF NOT EXISTS idx_cookies_checker ON cookies (status, last_checked_at);
