#!/usr/bin/env python3
"""
Minimal Netflix Login Bot — Entry point.

Supabase is the source of truth. The bot:
  - loads the cookie pool from Supabase at startup
  - serves /loginlink (quota checked on Supabase profiles)
  - runs the HTTP API server for the web app (check-cookie / batch-check)
"""

import logging
import threading
import time

from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from config import BOT_TOKEN, ADMIN_IDS
from supabase_client import load_cookies_from_supabase
from api_server import start_api_server
from handlers import (
    cmd_start,
    cmd_loginlink,
    cmd_lang,
    on_lang_callback,
    on_link_confirm_callback,
)
from proxies import start_proxy_scanner

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("NetflixBot")

# Tự reload cookie pool từ Supabase định kỳ để nhận cookie mới admin import
# mà không cần restart bot (bot chỉ load 1 lần lúc startup trước đây).
COOKIE_RELOAD_INTERVAL_SEC = 300  # 5 phút


def _start_cookie_reloader():
    def _loop():
        while True:
            time.sleep(COOKIE_RELOAD_INTERVAL_SEC)
            try:
                total = load_cookies_from_supabase()
                logger.info("Cookie pool auto-reloaded: %d cookies", total)
            except Exception as e:
                logger.warning("Cookie pool auto-reload failed: %s", e)

    t = threading.Thread(target=_loop, daemon=True, name="cookie-reloader")
    t.start()
    logger.info("Cookie auto-reloader started (every %ds)", COOKIE_RELOAD_INTERVAL_SEC)


USER_COMMANDS = [
    BotCommand("start", "Bắt đầu / Start"),
    BotCommand("loginlink", "Lấy link đăng nhập / Get login link"),
    BotCommand("lang", "Đổi ngôn ngữ / Change language"),
]


async def _setup_commands(app):
    try:
        bot = app.bot
        await bot.set_my_commands(USER_COMMANDS)
        for admin_id in ADMIN_IDS:
            await bot.set_my_commands(
                USER_COMMANDS,
                scope=__import__("telegram").BotCommandScopeChat(chat_id=admin_id),
            )
        logger.info("Command menu set")
    except Exception as e:
        logger.error("Failed to set commands menu: %s", e)


def main():
    print()
    print("─── 🔸 ───")
    print("  🎬 Netflix Login Bot (minimal)")
    print("─── 🔸 ───")
    print()

    # Load cookie pool from Supabase (source of truth)
    total = load_cookies_from_supabase()
    logger.info("Ready! %d cookies loaded from Supabase.", total)
    _start_cookie_reloader()
    start_proxy_scanner()

    request = HTTPXRequest(
        connect_timeout=30.0, read_timeout=30.0, write_timeout=30.0,
        pool_timeout=30.0, connection_pool_size=40,
    )
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .concurrent_updates(True)
        .post_init(_setup_commands)
        .build()
    )

    start_api_server(app.bot)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("loginlink", cmd_loginlink))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CallbackQueryHandler(on_lang_callback, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(on_link_confirm_callback, pattern="^link_(yes|no)$"))

    logger.info("🚀 Bot is running!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
