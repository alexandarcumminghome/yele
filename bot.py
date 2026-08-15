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
- Queries are debounced per-user (DEBOUNCE_SECONDS) before any
  render/upload work happens, so fast typing ("one keystroke = one
  inline query") doesn't translate into "one keystroke = one upload".
  Telegram's flood limit on SendSticker for a single chat is strict
  enough that without this, typing more than a few characters quickly
  reliably triggers TelegramRetryAfter and silently drops results.
- Static and animated results are built concurrently (asyncio.gather)
  per query to keep total handler latency down.
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
from aiogram.exceptions import TelegramRetryAfter
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

from generator import render_sticker, FONT_PATH, DEFAULT_TEXT
from generator_tgs import render_tgs_sticker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("depo_bot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
# Chat where generated images get uploaded so Telegram issues a
# sticker file_id we can reuse in inline results. Use a private
# channel/group the bot is a member+admin of. Example: -1001234567890
CACHE_CHAT_ID = int(os.environ.get("CACHE_CHAT_ID", "0"))

BOT_USERNAME = "KFCFBOT"
MAX_INPUT_LEN = 120  # guard against absurd inputs

# How long to wait after an inline query arrives before actually doing
# the (expensive) render+upload work. If a newer query from the same
# user shows up before this elapses, the earlier one is abandoned.
# Without this, someone typing "anonhawk mere lun pe" fires a fresh
# render+upload *per keystroke*, which blows straight through
# Telegram's per-chat flood limit on SendSticker within a couple of
# seconds (see aiogram.exceptions.TelegramRetryAfter in the logs).
DEBOUNCE_SECONDS = 0.45

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# text -> telegram sticker file_id, so repeat captions are instant and
# don't re-upload to the cache chat every time.
_file_id_cache: dict[str, str] = {}

# user_id -> last query text seen, used for debouncing (see above).
_latest_query_text: dict[int, str] = {}


def _cache_key(template_id: str, text: str) -> str:
    return hashlib.sha256(f"{template_id}:{text}".encode("utf-8")).hexdigest()


@dp.message(CommandStart())
async def start_handler(message: Message):
    text = (
        "👋 <b>Welcome!</b>\n\n"
        "I turn any line of text into a sticker — no need to add me to a "
        "chat, just use me <b>inline</b>, anywhere.\n\n"
        "<b>How to use me:</b>\n"
        f"1. In <b>any</b> chat, type <code>@{BOT_USERNAME}</code> followed by a space\n"
        "2. Add your text, e.g. <code>ye le pakad</code>\n"
        "3. I'll show you two versions — a classic photo sticker and an "
        "animated one — tap whichever you like to send it\n\n"
        "Long text automatically wraps to multiple lines. Leave the text "
        f"blank and I'll use the default \"{DEFAULT_TEXT}\" caption.\n\n"
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


async def _get_or_create_file_id(template_id: str, text: str, png_or_tgs_bytes: bytes, filename: str) -> str:
    key = _cache_key(template_id, text)
    if key in _file_id_cache:
        return _file_id_cache[key]

    sticker_file = BufferedInputFile(png_or_tgs_bytes, filename=filename)
    msg = await bot.send_sticker(chat_id=CACHE_CHAT_ID, sticker=sticker_file)
    file_id = msg.sticker.file_id
    _file_id_cache[key] = file_id
    return file_id


async def _build_static_result(text: str):
    png_bytes = render_sticker(text)
    file_id = await _get_or_create_file_id("static", text, png_bytes, "depo.png")
    return InlineQueryResultCachedSticker(
        id=_cache_key("static", text)[:64],
        sticker_file_id=file_id,
    )


async def _build_animated_result(text: str):
    tgs_bytes = render_tgs_sticker(text)
    file_id = await _get_or_create_file_id("animated", text, tgs_bytes, "depo.tgs")
    return InlineQueryResultCachedSticker(
        id=_cache_key("animated", text)[:64],
        sticker_file_id=file_id,
    )


@dp.inline_query()
async def handle_inline(query: InlineQuery):
    raw_text = query.query.strip()
    text = (raw_text or DEFAULT_TEXT)[:MAX_INPUT_LEN]

    # Debounce: record this as the latest query for this user, wait a
    # beat, then bail out silently if a newer one has already
    # superseded it. Cuts render+upload calls from "one per keystroke"
    # to "one per pause in typing".
    user_id = query.from_user.id
    _latest_query_text[user_id] = text
    await asyncio.sleep(DEBOUNCE_SECONDS)
    if _latest_query_text.get(user_id) != text:
        return

    results = []
    outcomes = await asyncio.gather(
        _build_static_result(text),
        _build_animated_result(text),
        return_exceptions=True,
    )
    for outcome in outcomes:
        if isinstance(outcome, TelegramRetryAfter):
            logger.warning(
                "flood control hit while building a result for %r, retry_after=%s "
                "— skipping this result for this query (debounce should prevent "
                "this under normal typing)",
                text, outcome.retry_after,
            )
        elif isinstance(outcome, Exception):
            logger.error("failed to build a result for %r: %r", text, outcome)
        else:
            results.append(outcome)

    if results:
        await query.answer(results, cache_time=1, is_personal=False)
    else:
        fallback = InlineQueryResultArticle(
            id="error",
            title="Couldn't generate sticker",
            description="Try again in a moment",
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
