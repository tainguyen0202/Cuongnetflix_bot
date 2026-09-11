#!/usr/bin/env python3
"""
Minimal Netflix Login Bot — Entry point.

Supabase is the source of truth. The bot:
  - loads the cookie pool from Supabase at startup
  - serves /loginlink (quota checked on Supabase profiles)
  - runs the HTTP API server for the web app (check-cookie / batch-check)
"""

import logging

from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from config import BOT_TOKEN, ADMIN_IDS
from supabase_client import load_cookies_from_supabase
from api_server import start_api_server
from handlers import cmd_start, cmd_loginlink

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("NetflixBot")


USER_COMMANDS = [
    BotCommand("start", "Bắt đầu / Start"),
    BotCommand("loginlink", "Lấy link đăng nhập / Get login link"),
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

    logger.info("🚀 Bot is running!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
