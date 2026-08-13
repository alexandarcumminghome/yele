"""
generator.py
Renders the "Ye le depo" style meme template with custom text.

The template (template.png) is a 512x512 RGBA image with a white
rounded caption box baked into the bottom. We paint over the box
(same off-white) and re-draw it with the user's text, auto-wrapping
to two lines and auto-shrinking the font so it always fits.
"""

from PIL import Image, ImageDraw, ImageFont
import io
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "template.png")

# Bundled in the repo (fonts/DejaVuSans-Bold.ttf) so rendering doesn't
# depend on whatever fonts happen to be installed on the host. We still
# fall back to a few common system paths, and finally to PIL's built-in
# bitmap font, so the bot degrades gracefully instead of crashing.
_FONT_CANDIDATES = [
    os.path.join(BASE_DIR, "fonts", "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]
FONT_PATH = next((p for p in _FONT_CANDIDATES if os.path.isfile(p)), None)

# Box geometry measured from the template (x0, y0, x1, y1)
BOX = (40, 378, 466, 497)
BOX_FILL = (255, 255, 255, 255)
BOX_RADIUS = 28
TEXT_COLOR = (17, 17, 17, 255)

PADDING_X = 24
PADDING_Y = 14
MAX_FONT_SIZE = 64
MIN_FONT_SIZE = 22
LINE_SPACING = 6


def _load_font(size: int) -> ImageFont.ImageFont:
    if FONT_PATH:
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except OSError:
            pass
    # Last-resort fallback so a missing font file never crashes a render;
    # this won't scale with `size` but at least produces output.
    return ImageFont.load_default()


def _wrap_to_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int):
    """Greedy word-wrap. Returns list of lines (max ~2 preferred, but will
    add more if the text is very long rather than losing content)."""
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        w = draw.textbbox((0, 0), trial, font=font)[2]
        if w <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_height: int):
    """Find the largest font size (within bounds) such that the text
    wraps to at most 2 lines and fits in the box. Falls back to more
    lines at MIN_FONT_SIZE if the text is extremely long."""
    for size in range(MAX_FONT_SIZE, MIN_FONT_SIZE - 1, -2):
        font = _load_font(size)
        lines = _wrap_to_lines(draw, text, font, max_width)
        if len(lines) > 2:
            continue
        line_height = draw.textbbox((0, 0), "Ag", font=font)[3]
        total_height = line_height * len(lines) + LINE_SPACING * (len(lines) - 1)
        if total_height <= max_height:
            return font, lines

    # Long-text fallback: use min size, allow as many lines as needed
    font = _load_font(MIN_FONT_SIZE)
    lines = _wrap_to_lines(draw, text, font, max_width)
    return font, lines


def render_sticker(text: str) -> bytes:
    """Returns PNG bytes of the template with `text` drawn into the caption box."""
    img = Image.open(TEMPLATE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Blank the existing caption box
    draw.rounded_rectangle(BOX, radius=BOX_RADIUS, fill=BOX_FILL)

    x0, y0, x1, y1 = BOX
    max_width = (x1 - x0) - 2 * PADDING_X
    max_height = (y1 - y0) - 2 * PADDING_Y

    text = text.strip() or "Ye le depo"
    font, lines = _fit_text(draw, text, max_width, max_height)

    line_height = draw.textbbox((0, 0), "Ag", font=font)[3]
    total_height = line_height * len(lines) + LINE_SPACING * (len(lines) - 1)
    cy = y0 + (y1 - y0 - total_height) / 2

    for line in lines:
        w = draw.textbbox((0, 0), line, font=font)[2]
        cx = x0 + ((x1 - x0) - w) / 2
        draw.text((cx, cy), line, font=font, fill=TEXT_COLOR)
        cy += line_height + LINE_SPACING

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


if __name__ == "__main__":
    # quick local tests
    for i, sample in enumerate([
        "Ye le pakad",
        "Ye le depo bhai kya scene hai",
        "Chai",
        "Mujhe bhi ek chahiye yaar please jaldi bhej do",
    ]):
        data = render_sticker(sample)
        with open(f"test_{i}.png", "wb") as f:
            f.write(data)
        print("wrote", f"test_{i}.png", "for text:", sample)
