"""
bot.py — Inline "Ye le depo" meme sticker bot (aiogram 3.x)

How it works
------------
Telegram's inline mode (answer_inline_query) needs each result to point
at either a public image URL or a `file_id` already known to Telegram.
Since we generate a *new* image per query, we can't use a URL (would
need public hosting) — so we upload the freshly rendered PNG to a
private "cache" chat via bot.send_photo(), grab the file_id Telegram
gives back, and hand that to InlineQueryResultCachedPhoto. This is the
standard pattern for dynamic-content inline bots.

Setup
-----
1. Create a private Telegram channel (or just use Saved Messages / any
   chat the bot is in) to act as the cache store. Add the bot as admin.
2. Put the numeric chat id in CACHE_CHAT_ID below (or env var).
3. pip install aiogram==3.28.0 pillow
4. Set BOT_TOKEN env var (from BotFather) and run: python3 bot.py

Notes
-----
- A small LRU-ish in-memory cache maps text -> file_id so repeated
  queries for the same caption don't re-upload every time.
- inline_query.answer has a ~10s budget from Telegram before the query
  is considered stale, so we cap generation/upload time and results.
- cache_time=1 keeps Telegram from over-caching results client-side
  since captions are effectively infinite in variety.
"""

import asyncio
import hashlib
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.types import (
    InlineQuery,
    InlineQueryResultCachedPhoto,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from aiogram.enums import ParseMode

from generator import render_sticker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("depo_bot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
# Chat where generated images get uploaded so Telegram issues a file_id
# we can reuse in inline results. Use a private channel/group the bot
# is a member+admin of. Example: -1001234567890
CACHE_CHAT_ID = int(os.environ.get("CACHE_CHAT_ID", "0"))

DEFAULT_TEXT = "Ye le depo"
MAX_INPUT_LEN = 120  # guard against absurd inputs

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# text -> telegram file_id, so repeat captions are instant and don't
# re-upload to the cache chat every time.
_file_id_cache: dict[str, str] = {}


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _get_or_create_file_id(text: str) -> str:
    key = _cache_key(text)
    if key in _file_id_cache:
        return _file_id_cache[key]

    png_bytes = render_sticker(text)
    from aiogram.types import BufferedInputFile

    photo = BufferedInputFile(png_bytes, filename="depo.png")
    msg = await bot.send_photo(chat_id=CACHE_CHAT_ID, photo=photo)
    file_id = msg.photo[-1].file_id
    _file_id_cache[key] = file_id
    return file_id


@dp.inline_query()
async def handle_inline(query: InlineQuery):
    raw_text = query.query.strip()
    text = (raw_text or DEFAULT_TEXT)[:MAX_INPUT_LEN]

    try:
        file_id = await _get_or_create_file_id(text)
        result = InlineQueryResultCachedPhoto(
            id=_cache_key(text)[:64],
            photo_file_id=file_id,
        )
        await query.answer([result], cache_time=1, is_personal=False)
    except Exception:
        logger.exception("failed to build inline result for %r", text)
        fallback = InlineQueryResultArticle(
            id="error",
            title="Couldn't generate sticker",
            description="Try again with shorter text",
            input_message_content=InputTextMessageContent(
                message_text="⚠️ Couldn't generate that one, try again."
            ),
        )
        await query.answer([fallback], cache_time=1, is_personal=True)


async def main():
    if not CACHE_CHAT_ID:
        raise RuntimeError(
            "Set CACHE_CHAT_ID to a chat/channel id the bot can post images into "
            "(used to obtain file_ids for inline results)."
        )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
