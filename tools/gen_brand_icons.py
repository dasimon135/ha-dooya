"""Generate the brand icon set for the Dooya RF Covers integration.

Produces (under custom_components/dooya/brand/):
  icon.png (256), icon@2x.png (512), dark_icon.png, dark_icon@2x.png,
  logo.png, dark_logo.png

Design: rounded-square gradient background, white roller-shutter glyph with
RF waves — matching the visual style of the ha-rf-fan brand icons.

Usage:  python tools/gen_brand_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "dooya" / "brand"

# Sunset/terracotta gradient — evokes shutters + warmth, distinct from
# the blue used by ha-rf-fan.
LIGHT_GRADIENT = ((242, 165, 65), (217, 91, 67))    # amber -> coral
DARK_GRADIENT = ((196, 120, 38), (150, 55, 38))     # deeper variant for dark theme

SS = 4  # supersampling factor for antialiasing


def _gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        for x in range(size):
            px[x, y] = color
    return img


def _draw_glyph(draw: ImageDraw.ImageDraw, s: float) -> None:
    """Draw the shutter window + RF waves. `s` scales 256-based coordinates."""
    white = (255, 255, 255, 255)

    # Window frame
    wx0, wy0, wx1, wy1 = 88 * s, 66 * s, 216 * s, 208 * s
    frame = 10 * s
    draw.rounded_rectangle(
        (wx0, wy0, wx1, wy1), radius=12 * s, outline=white, width=round(frame)
    )

    # Shutter slats: horizontal bars filling the upper ~55% of the window
    ix0, ix1 = wx0 + frame, wx1 - frame
    iy0 = wy0 + frame
    slat_h, gap = 9 * s, 6 * s
    curtain_bottom = wy0 + (wy1 - wy0) * 0.58
    y = iy0
    while y + slat_h <= curtain_bottom:
        draw.rectangle((ix0, y, ix1, y + slat_h), fill=white)
        y += slat_h + gap
    # Bottom bar of the curtain, slightly thicker
    draw.rectangle((ix0, y, ix1, y + slat_h * 1.35), fill=white)

    # RF waves: dot + three arcs radiating to the upper-left
    cx, cy = 56 * s, 56 * s
    draw.ellipse((cx - 9 * s, cy - 9 * s, cx + 9 * s, cy + 9 * s), fill=white)
    for radius in (26, 44, 62):
        r = radius * s
        draw.arc(
            (cx - r, cy - r, cx + r, cy + r),
            start=150,
            end=300,
            fill=white,
            width=round(9 * s),
        )


def make_icon(size: int, gradient: tuple) -> Image.Image:
    big = size * SS
    s = big / 256

    grad = _gradient(big, *gradient)

    # Rounded-square mask
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=56 * s, fill=255)

    icon = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    icon.paste(grad, (0, 0), mask)

    _draw_glyph(ImageDraw.Draw(icon), s)
    return icon.resize((size, size), Image.LANCZOS)


def make_logo(icon: Image.Image, text_color: tuple) -> Image.Image:
    """Icon + 'Dooya RF' wordmark, 256 px tall."""
    height = 256
    icon_small = icon.resize((200, 200), Image.LANCZOS)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 96)
    except OSError:
        font = ImageFont.load_default(size=96)

    text = "Dooya RF"
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = tmp.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]

    width = 200 + 40 + text_w + 24
    logo = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    logo.paste(icon_small, (0, (height - 200) // 2), icon_small)
    draw = ImageDraw.Draw(logo)
    text_y = (height - (bbox[3] - bbox[1])) // 2 - bbox[1]
    draw.text((240, text_y), text, font=font, fill=text_color)
    return logo


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    icon = make_icon(256, LIGHT_GRADIENT)
    icon.save(OUT_DIR / "icon.png")
    make_icon(512, LIGHT_GRADIENT).save(OUT_DIR / "icon@2x.png")

    dark = make_icon(256, DARK_GRADIENT)
    dark.save(OUT_DIR / "dark_icon.png")
    make_icon(512, DARK_GRADIENT).save(OUT_DIR / "dark_icon@2x.png")

    make_logo(icon, (45, 45, 45, 255)).save(OUT_DIR / "logo.png")
    make_logo(dark, (255, 255, 255, 255)).save(OUT_DIR / "dark_logo.png")

    print(f"Icons written to {OUT_DIR}")


if __name__ == "__main__":
    main()
