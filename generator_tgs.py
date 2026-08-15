"""
generator_tgs.py
Renders the animated "Pepe holding a sign" template (template_pepe.tgs)
with custom text, by replacing the placeholder `testo_utente` layer's
vector letterforms with freshly generated ones for the user's text.

Why vector letters instead of a Lottie text layer
--------------------------------------------------
Telegram's animated-sticker renderer (rlottie) does not reliably
support live text layers. The template's original author already
worked around this by hand-converting the placeholder caption
("Hoted") into vector shapes (visible as the `testo_utente` layer).
We follow the same approach: convert the user's text to bezier
letterforms with a real font, then splice those shapes into the
animation in place of the placeholder — the sign board, Pepe, and the
bob/arm animation are untouched.

Box geometry
------------
Measured from the template's sign-board layer (index 2): a rectangle
centered at (254.412, 88.615) sized 497.39 x 154.362, in the same
local coordinate space the testo_utente layer's shapes already live
in (testo_utente is parented to the board layer with zero own offset).
"""

import gzip
import io
import json
import os

from lottie.parsers.tgs import parse_tgs
from lottie.nvector import NVector
from lottie.objects.shapes import Fill, Group

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "template_pepe.tgs")
FONT_PATH = os.path.join(BASE_DIR, "fonts", "DejaVuSans-Bold.ttf")

# Sign-board rectangle in local coords (see module docstring)
BOX_CENTER = NVector(254.412, 88.615)
BOX_W, BOX_H = 497.39, 154.362
PAD_X_FRAC, PAD_Y_FRAC = 0.09, 0.14
AVAILABLE_W = BOX_W * (1 - 2 * PAD_X_FRAC)
AVAILABLE_H = BOX_H * (1 - 2 * PAD_Y_FRAC)

MAX_FONT_SIZE = 100
MIN_FONT_SIZE = 34
FONT_STEP = 4
LINE_PITCH_MULT = 1.18  # spacing between baselines relative to font size

TEXT_COLOR = NVector(0.07, 0.07, 0.07)
DEFAULT_TEXT = "Hoted"

_renderer = None


def _get_renderer():
    global _renderer
    if _renderer is None:
        from lottie.utils.font import RawFontRenderer

        _renderer = RawFontRenderer(FONT_PATH)
    return _renderer


def _line_width(renderer, text, size):
    g = renderer.render(text, size, pos=NVector(0, 0))
    return g.bounding_box().width if g.shapes else 0


def _wrap_lines(renderer, text, size, max_width):
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if _line_width(renderer, trial, size) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_text(renderer, text, max_width, max_height):
    for size in range(MAX_FONT_SIZE, MIN_FONT_SIZE - 1, -FONT_STEP):
        lines = _wrap_lines(renderer, text, size, max_width)
        if len(lines) > 2:
            continue
        pitch = size * LINE_PITCH_MULT
        block_height = pitch * len(lines)
        if block_height <= max_height:
            return size, lines

    # Long-text fallback: smallest size, however many lines it takes
    size = MIN_FONT_SIZE
    lines = _wrap_lines(renderer, text, size, max_width)
    return size, lines


def _build_text_group(text: str) -> Group:
    renderer = _get_renderer()
    text = text.strip() or DEFAULT_TEXT

    size, lines = _fit_text(renderer, text, AVAILABLE_W, AVAILABLE_H)
    multiline = "\n".join(lines)

    group = renderer.render(multiline, size, pos=NVector(0, 0))
    group.add_shape(Fill(TEXT_COLOR))
    group.name = "testo_utente"

    # Horizontally center each line independently.
    for line in group.shapes:
        if type(line).__name__ != "Group":
            continue
        bb = line.bounding_box()
        if bb.isnull():
            continue
        target_x1 = BOX_CENTER.x - bb.width / 2
        line.transform.position.value = NVector(target_x1 - bb.x1, 0)

    # Vertically center the whole block.
    overall = group.bounding_box()
    if not overall.isnull():
        target_y1 = BOX_CENTER.y - overall.height / 2
        group.transform.position.value = NVector(0, target_y1 - overall.y1)

    return group


def render_tgs_sticker(text: str) -> bytes:
    """Returns gzip-compressed Lottie JSON (.tgs) bytes with `text`
    baked into the sign board, animation intact."""
    anim = parse_tgs(TEMPLATE_PATH)

    target_layer = None
    for layer in anim.layers:
        if layer.name == "testo_utente":
            target_layer = layer
            break
    if target_layer is None:
        raise RuntimeError("template_pepe.tgs has no 'testo_utente' layer")

    new_group = _build_text_group(text)
    target_layer.shapes = [new_group]

    raw = json.dumps(anim.to_dict(), separators=(",", ":"))
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
        gz.write(raw.encode("utf-8"))
    return out.getvalue()


if __name__ == "__main__":
    for i, sample in enumerate(["Ye le pakad", "Chai", "Mujhe bhi ek chahiye yaar jaldi"]):
        data = render_tgs_sticker(sample)
        with open(f"test_tgs_{i}.tgs", "wb") as f:
            f.write(data)
        print("wrote", f"test_tgs_{i}.tgs", "for:", sample, "bytes:", len(data))
