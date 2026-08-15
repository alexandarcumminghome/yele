"""
diagnose_animated.py — run this directly on the server to isolate why
the animated sticker isn't showing up in inline results.

Usage:
    cd /root/yele
    python3 diagnose_animated.py

Requires BOT_TOKEN and CACHE_CHAT_ID env vars (same as bot.py).
"""

import asyncio
import os
import sys

from aiogram import Bot
from aiogram.types import BufferedInputFile


async def main():
    bot_token = os.environ["BOT_TOKEN"]
    cache_chat_id = int(os.environ["CACHE_CHAT_ID"])
    bot = Bot(token=bot_token)

    print("1. Importing generator_tgs...")
    try:
        from generator_tgs import render_tgs_sticker
        print("   OK")
    except Exception as e:
        print("   FAILED at import:", repr(e))
        sys.exit(1)

    print("2. Rendering test .tgs...")
    try:
        data = render_tgs_sticker("diagnostic test")
        print(f"   OK, {len(data)} bytes")
    except Exception as e:
        print("   FAILED at render:", repr(e))
        sys.exit(1)

    print("3. Uploading to CACHE_CHAT_ID via send_sticker...")
    try:
        sticker_file = BufferedInputFile(data, filename="diag.tgs")
        msg = await bot.send_sticker(chat_id=cache_chat_id, sticker=sticker_file)
        print("   OK, file_id:", msg.sticker.file_id)
        print("   is_animated:", msg.sticker.is_animated)
    except Exception as e:
        print("   FAILED at send_sticker:", repr(e))
        sys.exit(1)

    print("\nAll steps succeeded — the animated pipeline works standalone.")
    print("If it's still missing from inline results, the issue is likely")
    print("in handle_inline() itself, or a per-query timing/exception")
    print("that only shows up under real inline-query conditions.")

    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
