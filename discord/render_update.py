#!/usr/bin/env python3
"""Render a consistent 1080x1080 ESTLELA support update image."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1080
HEIGHT = 1080

CREAM = "#FFFDF5"
NAVY = "#0A3458"
PINK = "#EF2C7C"
PINK_SOFT = "#FFF0F6"
CYAN = "#26B7D5"
CYAN_SOFT = "#ECFAFD"
YELLOW = "#FFD53D"
YELLOW_SOFT = "#FFF9DF"
GREEN = "#2CB66D"
GREEN_SOFT = "#EEFBF4"
WHITE = "#FFFFFF"
MUTED = "#617387"


FONT_CANDIDATES = {
    "regular": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "bold": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
}


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = "bold" if bold else "regular"
    custom = os.environ.get("ESTLELA_FONT_BOLD" if bold else "ESTLELA_FONT_REGULAR")
    candidates = ([custom] if custom else []) + FONT_CANDIDATES[key]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    raise RuntimeError("No suitable font found. Install fonts-noto-cjk.")


def text_width(draw: ImageDraw.ImageDraw, text: str, selected_font: ImageFont.FreeTypeFont) -> float:
    return draw.textlength(text, font=selected_font)


def wrap_text(
    draw: ImageDraw.ImageDraw,
    value: str,
    selected_font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    value = re.sub(r"\s+", " ", value.strip())
    if not value:
        return [""]

    lines: list[str] = []
    current = ""
    for char in value:
        candidate = current + char
        if current and text_width(draw, candidate, selected_font) > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)

    if len(lines) <= max_lines:
        return lines

    lines = lines[:max_lines]
    last = lines[-1]
    while last and text_width(draw, last + "…", selected_font) > max_width:
        last = last[:-1]
    lines[-1] = last.rstrip() + "…"
    return lines


def draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    xy: tuple[int, int],
    selected_font: ImageFont.FreeTypeFont,
    fill: str,
    line_gap: int,
) -> int:
    x, y = xy
    bbox = draw.textbbox((0, 0), "あAg", font=selected_font)
    line_height = bbox[3] - bbox[1]
    for line in lines:
        draw.text((x, y), line, font=selected_font, fill=fill)
        y += line_height + line_gap
    return y


def type_palette(kind: str) -> tuple[str, str]:
    normalized = kind.strip()
    if "新" in normalized:
        return PINK, PINK_SOFT
    if "修正" in normalized or "不具合" in normalized:
        return GREEN, GREEN_SOFT
    if "改善" in normalized:
        return CYAN, CYAN_SOFT
    return "#D79E00", YELLOW_SOFT


def validate_payload(payload: dict[str, Any]) -> None:
    release_id = str(payload.get("release_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", release_id):
        raise ValueError("release_id must contain only letters, numbers, dot, underscore, or hyphen")

    headline = str(payload.get("headline", "")).strip()
    if not headline or len(headline) > 90:
        raise ValueError("headline is required and must be 90 characters or fewer")

    changes = payload.get("changes")
    if not isinstance(changes, list) or not 1 <= len(changes) <= 3:
        raise ValueError("changes must contain 1 to 3 items")

    for item in changes:
        if not isinstance(item, dict):
            raise ValueError("each change must be an object")
        if not str(item.get("title", "")).strip():
            raise ValueError("each change requires a title")
        if not str(item.get("benefit", "")).strip():
            raise ValueError("each change requires a benefit")

    message = str(payload.get("message", "")).strip()
    if not message or len(message) > 1900:
        raise ValueError("message is required and must be 1900 characters or fewer")

    site_url = str(payload.get("site_url", ""))
    if not site_url.startswith("https://"):
        raise ValueError("site_url must be an HTTPS URL")


def render_update(payload: dict[str, Any], output_path: str | Path) -> Path:
    validate_payload(payload)

    image = Image.new("RGB", (WIDTH, HEIGHT), CREAM)
    draw = ImageDraw.Draw(image)

    # Soft brand circles outside the main card.
    draw.ellipse((-95, -105, 235, 225), fill="#FFD8E9")
    draw.ellipse((865, -100, 1195, 230), fill="#9DEAF6")
    draw.ellipse((-125, 790, 165, 1080), fill="#8DDEEA")
    draw.ellipse((890, 840, 1170, 1120), fill="#FFE077")

    # Main card and subtle shadow.
    draw.rounded_rectangle((57, 50, 1031, 1036), radius=38, fill="#DFE5E8")
    draw.rounded_rectangle((45, 38, 1019, 1024), radius=38, fill=WHITE, outline=PINK, width=5)

    # Brand header.
    draw.ellipse((82, 75, 154, 147), fill=PINK, outline=NAVY, width=2)
    e_font = font(42, bold=True)
    draw.text((118, 111), "E", font=e_font, fill=WHITE, anchor="mm")
    draw.text((174, 78), "ESTLELA", font=font(29, bold=True), fill=PINK)
    draw.text((176, 116), "BUSINESS SUPPORT", font=font(14, bold=True), fill=NAVY)

    date_text = str(payload.get("date", "")).strip() or "TODAY"
    badge_left = 760
    draw.rounded_rectangle((badge_left, 78, 968, 140), radius=31, fill=YELLOW_SOFT, outline=YELLOW, width=3)
    draw.text((864, 109), date_text, font=font(19, bold=True), fill=NAVY, anchor="mm")

    draw.text((82, 178), "ESTLELA SUPPORT UPDATE", font=font(20, bold=True), fill=CYAN)

    headline_font = font(55, bold=True)
    headline_lines = wrap_text(draw, str(payload["headline"]), headline_font, 850, 2)
    headline_bottom = draw_lines(draw, headline_lines, (82, 222), headline_font, NAVY, 10)
    underline_y = min(headline_bottom + 8, 355)
    draw.rounded_rectangle((82, underline_y, 446, underline_y + 13), radius=6, fill=YELLOW)

    changes = payload["changes"]
    cards_top = max(underline_y + 43, 378)
    cards_bottom = 888
    gap = 16
    card_height = int((cards_bottom - cards_top - gap * (len(changes) - 1)) / len(changes))

    for index, item in enumerate(changes):
        top = cards_top + index * (card_height + gap)
        bottom = top + card_height
        accent, soft = type_palette(str(item.get("type", "更新")))
        draw.rounded_rectangle((82, top, 938, bottom), radius=26, fill=soft, outline=accent, width=3)

        kind = str(item.get("type", "更新")).strip()[:8]
        kind_font = font(18, bold=True)
        kind_width = int(text_width(draw, kind, kind_font)) + 42
        draw.rounded_rectangle((108, top + 20, 108 + kind_width, top + 61), radius=20, fill=accent)
        draw.text((129, top + 40), kind, font=kind_font, fill=WHITE, anchor="lm")

        title_font = font(31, bold=True)
        title_x = 132 + kind_width
        title_lines = wrap_text(draw, str(item["title"]), title_font, 902 - title_x, 1)
        draw.text((title_x, top + 41), title_lines[0], font=title_font, fill=NAVY, anchor="lm")

        benefit_font = font(24)
        benefit_lines = wrap_text(draw, str(item["benefit"]), benefit_font, 790, 2)
        draw_lines(draw, benefit_lines, (110, top + 79), benefit_font, MUTED, 6)

    # CTA/footer.
    draw.rounded_rectangle((82, 922, 938, 995), radius=36, fill=PINK)
    draw.text(
        (510, 948),
        "詳しくはエステレラ サポートサイトへ",
        font=font(27, bold=True),
        fill=WHITE,
        anchor="mm",
    )
    draw.text(
        (510, 979),
        "estlela-business-support.honotoku.chatgpt.site",
        font=font(14),
        fill=WHITE,
        anchor="mm",
    )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)
    return destination


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("payload", help="Path to an update payload JSON file")
    parser.add_argument("output", help="Output PNG path")
    args = parser.parse_args()

    with open(args.payload, "r", encoding="utf-8") as source:
        payload = json.load(source)
    path = render_update(payload, args.output)
    print(path)


if __name__ == "__main__":
    main()
