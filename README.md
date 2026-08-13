# Ye Le Depo — Inline Meme Sticker Bot

Generates the "Ye le depo" template with custom text and lets people
drop it into any chat via inline mode: `@yourbot ye le pakad`.

## Files
- `template.png` — base image (512×512)
- `generator.py` — draws custom text into the caption box (auto 2-line wrap, auto-shrink font for long text)
- `bot.py` — aiogram inline bot
- `requirements.txt`

## Setup

1. **Create the bot** with [@BotFather](https://t.me/BotFather):
   - `/newbot` → get your token
   - `/setinline` → enable inline mode, set a placeholder like `Type your caption...`
   - (optional) `/setinlinefeedback` if you want feedback stats later

2. **Create a cache chat.** Telegram inline results need a `file_id`,
   not raw bytes, so each freshly generated image is first sent to a
   private chat/channel to obtain a `file_id`, which is then reused.
   - Make a private channel, add your bot as admin
   - Send any message there, forward it to [@userinfobot](https://t.me/userinfobot) or use
     `getUpdates`/a helper script to read the channel's numeric ID (looks like `-1001234567890`)

3. **Install deps:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run:**
   ```bash
   export BOT_TOKEN="123456:ABC-your-token"
   export CACHE_CHAT_ID="-1001234567890"
   python3 bot.py
   ```

5. In any chat, type `@yourbot some text` — the bot returns the
   rendered image inline, tap to send.

## Behavior
- Empty query → falls back to the default "Ye le depo" caption
- Text auto-wraps to 2 lines; if it's too long even at the smallest
  font size, it wraps to more lines rather than clipping
- Input capped at 120 characters (`MAX_INPUT_LEN` in `bot.py`) to keep
  renders sane — tweak as you like
- Repeated captions reuse the cached `file_id` instead of re-rendering
  and re-uploading, so common phrases respond instantly

## Tuning the template
If you swap in a different base image, remeasure the caption box and
update `BOX` in `generator.py` (it's just an `(x0, y0, x1, y1)` box in
pixel coordinates on the 512×512 canvas).

## Scaling notes
- The in-memory `_file_id_cache` dict resets on restart — swap in
  Redis/SQLite if you want it persistent across deploys
- `answer_inline_query` has a short window (~10s) before Telegram
  drops the query, so keep the cache chat close (same DC) and avoid
  adding heavy work to the render path
