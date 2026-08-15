# Ye Le Depo — Inline Meme Sticker Bot

Generates two sticker styles from custom text and lets people drop
them into any chat via inline mode: `@KFCFBOT ye le pakad` shows both,
they tap whichever they want to send.

## Templates
- **Static** — the classic "Ye le depo" photo template (`template.png`)
- **Animated** — Pepe holding a bouncing sign (`template_pepe.tgs`),
  text is baked in as real vector letterforms so it animates cleanly

## Files
- `template.png` / `template_pepe.tgs` — base templates
- `generator.py` — draws custom text into the static template's caption box (auto-wrap, auto-shrink font)
- `generator_tgs.py` — replaces the animated template's placeholder text layer with freshly generated vector letterforms (same auto-wrap/auto-shrink logic, adapted for Lottie shapes)
- `fonts/DejaVuSans-Bold.ttf` — bundled so rendering doesn't depend on the host's system fonts
- `bot.py` — aiogram inline bot, returns both results per query
- `requirements.txt`

## Setup

1. **Create the bot** with [@BotFather](https://t.me/BotFather):
   - `/newbot` → get your token
   - `/setinline` → enable inline mode, set a placeholder like `Type your caption...`

2. **Create a cache chat.** Telegram inline results need a `file_id`,
   not raw bytes, so each freshly generated sticker (static or
   animated) is first sent to a private chat/channel via
   `send_sticker` to obtain a `file_id`, which is then reused.
   - Make a private channel, add your bot as admin
   - Read its numeric ID (looks like `-1001234567890`), e.g. via
     [@userinfobot](https://t.me/userinfobot) or `getUpdates`

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

5. In any chat, type `@KFCFBOT some text` — you'll see two results
   (static photo sticker, then animated Pepe sticker), tap either to
   send.

## Behavior
- Empty query → falls back to each template's own default caption
- Text auto-wraps to 2 lines per template's fit logic; if too long
  even at the smallest font size, wraps to more lines rather than
  clipping
- Input capped at 120 characters (`MAX_INPUT_LEN` in `bot.py`)
- Repeated captions reuse cached `file_id`s (separately per template)
  instead of re-rendering and re-uploading
- If one template fails to render for some input, the bot still
  returns the other result rather than failing the whole query

## Why the animated template uses vector letterforms, not a live text layer
Telegram's animated-sticker renderer (rlottie) doesn't reliably
support live Lottie text layers. `template_pepe.tgs` ships with a
placeholder layer (`testo_utente`) that was already hand-converted to
vector shapes for this reason — `generator_tgs.py` follows the same
approach, converting the user's text to bezier letterforms with
`lottie.utils.font` and splicing them in, leaving Pepe/the sign/the
bounce animation untouched.

## Tuning the templates
- Static: box geometry lives in `BOX` in `generator.py` — an
  `(x0, y0, x1, y1)` pixel box on the 512×512 canvas
- Animated: box geometry lives in `BOX_CENTER`/`BOX_W`/`BOX_H` in
  `generator_tgs.py`, measured from the sign-board layer's rectangle
  in local coordinates (same frame the `testo_utente` layer's shapes
  already use)

## Scaling notes
- The in-memory `_file_id_cache` dict resets on restart — swap in
  Redis/SQLite if you want it persistent across deploys
- `answer_inline_query` has a short window (~10s) before Telegram
  drops the query — two renders + two uploads per new caption is more
  work than before, so keep an eye on latency for very long/first-time
  queries
