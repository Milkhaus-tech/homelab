#!/usr/bin/env python3
"""Build both static 1200x630 landing-page cards with Pillow."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent.parent
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SITES = {
    "igembed": ("Instagram · embeds for Discord", "ig.milkhaus.net"),
    "xembed": ("X / Twitter · embeds for Discord", "x.milkhaus.net"),
}
SCALE = 2


def font(path, size):
    return ImageFont.truetype(path, size * SCALE)


def build(site):
    subline, host = SITES[site]
    size = (1200 * SCALE, 630 * SCALE)
    image = Image.new("RGB", size, "#0b0c0e")

    glow = Image.new("RGBA", size)
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-490 * SCALE, -530 * SCALE, 710 * SCALE, 670 * SCALE), fill=(226, 30, 55, 105))
    glow = glow.filter(ImageFilter.GaussianBlur(190 * SCALE))
    image = Image.alpha_composite(image.convert("RGBA"), glow)
    draw = ImageDraw.Draw(image)

    word = font(BOLD, 58)
    draw.text((64 * SCALE, 72 * SCALE), "TETO", font=word, fill="#e8eaed", anchor="la")
    teto_width = draw.textlength("TETO ", font=word)
    draw.text((64 * SCALE + teto_width, 72 * SCALE), "ZONE", font=word, fill="#e21e37", anchor="la")
    draw.text((64 * SCALE, 158 * SCALE), subline, font=font(FONT, 25), fill="#a8aeb6", anchor="la")
    draw.line((64 * SCALE, 216 * SCALE, 1136 * SCALE, 216 * SCALE), fill="#e21e37", width=2 * SCALE)

    box = (64 * SCALE, 274 * SCALE, 752 * SCALE, 386 * SCALE)
    draw.rounded_rectangle(box, radius=4 * SCALE, fill="#120e10", outline="#3a2026", width=SCALE)
    host_font = font(BOLD, 48)
    center = (408 * SCALE, 330 * SCALE)
    text_glow = Image.new("RGBA", size)
    tg = ImageDraw.Draw(text_glow)
    tg.text(center, host, font=host_font, fill=(226, 30, 55, 155), anchor="mm")
    image = Image.alpha_composite(image, text_glow.filter(ImageFilter.GaussianBlur(9 * SCALE)))
    draw = ImageDraw.Draw(image)
    draw.text((center[0] - SCALE, center[1]), host, font=host_font, fill=(255, 45, 70, 80), anchor="mm")
    draw.text((center[0] + SCALE, center[1]), host, font=host_font, fill=(40, 224, 255, 70), anchor="mm")
    draw.text(center, host, font=host_font, fill="white", anchor="mm")
    red, length, width = "#e21e37", 20 * SCALE, 2 * SCALE
    x1, y1, x2, y2 = box
    draw.line((x1, y1 + length, x1, y1, x1 + length, y1), fill=red, width=width)
    draw.line((x2 - length, y2, x2, y2, x2, y2 - length), fill=red, width=width)

    draw.text((64 * SCALE, 424 * SCALE), "change the host. paste into Discord.", font=font(FONT, 23), fill="#e8eaed", anchor="la")
    source = Image.open(ROOT / site / "static" / "teto-shocked.png").convert("RGB")
    art = ImageOps.fit(source, (320 * SCALE, 272 * SCALE), method=Image.Resampling.LANCZOS, centering=(.5, .32))
    mask = Image.new("L", art.size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, art.width - 1, art.height - 1), radius=12 * SCALE, fill=255)
    framed = Image.new("RGB", (324 * SCALE, 276 * SCALE), "#23262b")
    framed.paste(art, (2 * SCALE, 2 * SCALE), mask)
    image.paste(framed, (814 * SCALE, 256 * SCALE))
    draw = ImageDraw.Draw(image)
    draw.text((64 * SCALE, 568 * SCALE), "Teto artwork: Jamie Paige · CC BY 3.0", font=font(FONT, 16), fill="#a8aeb6", anchor="la")
    output = image.convert("RGB").resize((1200, 630), Image.Resampling.LANCZOS)
    output.save(ROOT / site / "static" / "og.png", optimize=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("site", choices=[*SITES, "both"], nargs="?", default="both")
    args = parser.parse_args()
    for name in SITES if args.site == "both" else (args.site,):
        build(name)
        print(ROOT / name / "static" / "og.png")
