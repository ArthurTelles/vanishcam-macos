"""Menu inicial no estilo dos apps da Apple: modo escuro, lista agrupada e fonte SF.

A imagem é desenhada com o dobro da resolução (SCALE) e a janela é aberta no
tamanho em pontos. Assim o texto fica nítido em telas Retina. O OpenCV devolve
as coordenadas do mouse na escala da imagem, por isso hit_test divide por SCALE.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


SCALE = 2
WIDTH, HEIGHT = 520, 440
LIST_LEFT, LIST_TOP, ROW_HEIGHT = 24, 112, 64
LIST_WIDTH = WIDTH - 2 * LIST_LEFT
RADIUS = 12

SF_FONT = Path("/System/Library/Fonts/SFNS.ttf")
EMOJI_FONT = Path("/System/Library/Fonts/Apple Color Emoji.ttc")

# Cores do sistema no modo escuro (Human Interface Guidelines).
BACKGROUND = (28, 28, 30)
GROUP = (44, 44, 46)
HOVER = (58, 58, 60)
SEPARATOR = (56, 56, 58)
LABEL = (255, 255, 255)
SECONDARY = (152, 152, 159)
ACCENT = (10, 132, 255)

ITEMS = (
    ("normal", "Normal Vanish", "Faça um V com os dedos para se dissolver", "✌️", (10, 132, 255)),
    ("naruto", "Naruto Vanish", "Junte as palmas: fumaça e tronco no lugar", "🍃", (48, 209, 88)),
    ("particles", "Particles", "Faça um V e vire fragmentos no vento", "✨", (191, 90, 242)),
    ("goku", "Goku", "Dois dedos na testa para se teletransportar", "⚡", (255, 159, 10)),
)


@lru_cache(maxsize=None)
def _font(size: float, weight: int) -> ImageFont.FreeTypeFont:
    pixels = round(size * SCALE)
    if not SF_FONT.is_file():
        return ImageFont.load_default(pixels)
    font = ImageFont.truetype(str(SF_FONT), pixels)
    try:
        # Eixos da SF: largura, tamanho óptico, GRAD e peso.
        font.set_variation_by_axes([100, min(max(size, 17), 96), 400, weight])
    except (OSError, ValueError):
        pass
    return font


@lru_cache(maxsize=None)
def _emoji(symbol: str, size: int) -> Image.Image | None:
    if not EMOJI_FONT.is_file():
        return None
    # A fonte de emoji da Apple é bitmap e só aceita alguns tamanhos, como 160.
    canvas = Image.new("RGBA", (180, 180), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text((0, 0), symbol, font=ImageFont.truetype(str(EMOJI_FONT), 160),
                                embedded_color=True)
    box = canvas.getbbox()
    if box is None:
        return None
    # Silhueta branca, como os símbolos sobre os quadrados coloridos do Ajustes.
    alpha = canvas.crop(box).getchannel("A")
    glyph = Image.new("RGBA", alpha.size, (255, 255, 255, 0))
    glyph.putalpha(alpha)
    glyph.thumbnail((size, size), Image.LANCZOS)
    return glyph


def _s(*values: float) -> tuple[int, ...]:
    return tuple(round(value * SCALE) for value in values)


def row_top(index: int) -> int:
    return LIST_TOP + index * ROW_HEIGHT


def hit_test(x: int, y: int) -> str | None:
    """Recebe coordenadas na escala da imagem e devolve o modo sob o mouse."""
    x, y = x / SCALE, y / SCALE
    if not LIST_LEFT <= x <= LIST_LEFT + LIST_WIDTH:
        return None
    for index, item in enumerate(ITEMS):
        if row_top(index) <= y < row_top(index) + ROW_HEIGHT:
            return item[0]
    return None


def _text(draw: ImageDraw.ImageDraw, position: tuple[float, float], text: str,
          size: float, weight: int, fill, anchor: str = "la") -> None:
    draw.text(_s(*position), text, font=_font(size, weight), fill=fill, anchor=anchor)


@lru_cache(maxsize=32)
def render(hovered: str | None = None, chosen: str | None = None) -> np.ndarray:
    """Devolve o menu em BGR, com o dobro da resolução de WIDTH x HEIGHT."""
    image = Image.new("RGB", _s(WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    _text(draw, (LIST_LEFT + 4, 40), "VanishCam", 28, 700, LABEL)
    _text(draw, (LIST_LEFT + 4, 78), "Escolha um efeito para começar.", 15, 400, SECONDARY)

    list_box = _s(LIST_LEFT, LIST_TOP, LIST_LEFT + LIST_WIDTH, row_top(len(ITEMS)))
    draw.rounded_rectangle(list_box, radius=RADIUS * SCALE, fill=GROUP)

    # Destaques são desenhados numa camada recortada pelo formato do grupo,
    # para respeitar os cantos arredondados da primeira e da última linha.
    highlight = Image.new("RGB", image.size, GROUP)
    highlight_draw = ImageDraw.Draw(highlight)
    active = chosen or hovered
    for index, item in enumerate(ITEMS):
        if item[0] == active:
            color = ACCENT if item[0] == chosen else HOVER
            highlight_draw.rectangle(_s(LIST_LEFT, row_top(index),
                                        LIST_LEFT + LIST_WIDTH, row_top(index) + ROW_HEIGHT), fill=color)
    clip = Image.new("L", image.size, 0)
    ImageDraw.Draw(clip).rounded_rectangle(list_box, radius=RADIUS * SCALE, fill=255)
    image.paste(highlight, (0, 0), clip)
    draw = ImageDraw.Draw(image)

    for index, (mode, title, subtitle, symbol, tint) in enumerate(ITEMS):
        top = row_top(index)
        selected = mode == chosen
        if index and active not in (mode, ITEMS[index - 1][0]):
            draw.line(_s(LIST_LEFT + 64, top, LIST_LEFT + LIST_WIDTH, top),
                      fill=SEPARATOR, width=1)

        icon = _s(LIST_LEFT + 14, top + 14, LIST_LEFT + 50, top + 50)
        draw.rounded_rectangle(icon, radius=9 * SCALE, fill=tint)
        glyph = _emoji(symbol, round(22 * SCALE))
        if glyph is not None:
            center_x, center_y = (icon[0] + icon[2]) // 2, (icon[1] + icon[3]) // 2
            image.paste(glyph, (center_x - glyph.width // 2, center_y - glyph.height // 2), glyph)

        _text(draw, (LIST_LEFT + 64, top + 14), title, 15, 600, LABEL)
        _text(draw, (LIST_LEFT + 64, top + 35), subtitle, 12.5, 400,
              (220, 235, 255) if selected else SECONDARY)

        chip = _s(LIST_LEFT + LIST_WIDTH - 44, top + 21, LIST_LEFT + LIST_WIDTH - 20, top + 43)
        draw.rounded_rectangle(chip, radius=6 * SCALE,
                               fill=(40, 110, 220) if selected else (72, 72, 74))
        _text(draw, (LIST_LEFT + LIST_WIDTH - 32, top + 32), str(index + 1), 12.5, 600,
              LABEL, anchor="mm")

    footer_y = row_top(len(ITEMS)) + 30
    if chosen is not None:
        _text(draw, (WIDTH / 2, footer_y), "Abrindo a câmera…", 13, 600, ACCENT, anchor="mm")
    else:
        _text(draw, (WIDTH / 2, footer_y),
              "Clique ou pressione 1 a 4. Durante o vídeo, M volta a este menu.",
              12, 400, SECONDARY, anchor="mm")

    return np.ascontiguousarray(np.asarray(image)[:, :, ::-1])
