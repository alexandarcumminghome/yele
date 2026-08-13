"""
bot.py — Inline "Ye le depo" meme sticker bot (aiogram 3.x)

How it works
------------
Telegram's inline mode (answer_inline_query) needs each result to point
at either a public asset URL or a `file_id` already known to Telegram.
Since we generate a *new* image per query, we can't use a URL — so we
upload the freshly rendered PNG to a private "cache" chat via
bot.send_sticker(), grab the sticker file_id Telegram gives back, and
hand that to InlineQueryResultCachedSticker. This is the standard
pattern for dynamic-content inline sticker bots.

Note: a *sticker* file_id (from send_sticker) is a different object
type from a *photo* file_id (from send_photo) — InlineQueryResult
CachedSticker only accepts the former, which is why results must be
uploaded as stickers, not photos.

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
- Telegram requires static stickers to be PNG/WEBP with one side
  exactly 512px and the other <=512px; our 512x512 RGBA template
  satisfies that as-is.
"""

import asyncio
import hashlib
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)

from generator import render_sticker, FONT_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("depo_bot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
# Chat where generated images get uploaded so Telegram issues a
# sticker file_id we can reuse in inline results. Use a private
# channel/group the bot is a member+admin of. Example: -1001234567890
CACHE_CHAT_ID = int(os.environ.get("CACHE_CHAT_ID", "0"))

BOT_USERNAME = "KFCFBOT"
DEFAULT_TEXT = "Ye le depo"
MAX_INPUT_LEN = 120  # guard against absurd inputs

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# text -> telegram sticker file_id, so repeat captions are instant and
# don't re-upload to the cache chat every time.
_file_id_cache: dict[str, str] = {}


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dp.message(CommandStart())
async def start_handler(message: Message):
    text = (
        "👋 <b>Welcome!</b>\n\n"
        "I turn any line of text into a \"Ye le depo\" sticker — no need "
        "to add me to a chat, just use me <b>inline</b>, anywhere.\n\n"
        "<b>How to use me:</b>\n"
        f"1. In <b>any</b> chat, type <code>@{BOT_USERNAME}</code> followed by a space\n"
        "2. Add your text, e.g. <code>ye le pakad</code>\n"
        "3. Tap the sticker that pops up to send it\n\n"
        "Long text automatically wraps to two lines. Leave the text blank "
        f"and I'll use the default \"{DEFAULT_TEXT}\" caption.\n\n"
        "👇 Try it right now:"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✨ Try it now",
                    switch_inline_query_current_chat="ye le pakad",
                )
            ]
        ]
    )
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


async def _get_or_create_file_id(text: str) -> str:
    key = _cache_key(text)
    if key in _file_id_cache:
        return _file_id_cache[key]

    png_bytes = render_sticker(text)
    sticker_file = BufferedInputFile(png_bytes, filename="depo.png")
    msg = await bot.send_sticker(chat_id=CACHE_CHAT_ID, sticker=sticker_file)
    file_id = msg.sticker.file_id
    _file_id_cache[key] = file_id
    return file_id


@dp.inline_query()
async def handle_inline(query: InlineQuery):
    raw_text = query.query.strip()
    text = (raw_text or DEFAULT_TEXT)[:MAX_INPUT_LEN]

    try:
        file_id = await _get_or_create_file_id(text)
        result = InlineQueryResultCachedSticker(
            id=_cache_key(text)[:64],
            sticker_file_id=file_id,
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
    if not FONT_PATH:
        logger.warning(
            "No usable font file found (checked bundled fonts/ dir and common "
            "system paths). Falling back to PIL's default bitmap font, which "
            "won't scale/wrap properly. Make sure fonts/DejaVuSans-Bold.ttf "
            "shipped with the repo."
        )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
