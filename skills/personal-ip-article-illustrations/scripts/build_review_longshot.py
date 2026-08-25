#!/usr/bin/env python3
"""Build a non-destructive vertical review sheet from generated illustrations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:
    raise SystemExit("Pillow is required: python3 -m pip install Pillow") from exc


DEFAULT_FONTS = (
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def next_available(path: Path) -> Path:
    if not path.exists():
        return path
    for version in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-v{version}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find an available versioned path for {path}")


def has_cjk_glyph(font_path: Path) -> bool:
    font = ImageFont.truetype(str(font_path), 32)
    target = font.getmask("审")
    missing = font.getmask("\u0378")
    return (target.size, bytes(target)) != (missing.size, bytes(missing))


def choose_font(explicit: str | None) -> Path:
    candidates = (explicit,) if explicit else DEFAULT_FONTS
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            path = Path(candidate)
            if has_cjk_glyph(path):
                return path
    raise FileNotFoundError("No usable font found. Pass --font with a CJK-capable font.")


def resolve_item_path(raw: str, spec_dir: Path) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = spec_dir / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Illustration not found: {path}")
    return path


def fit_on_white(source: Image.Image, width: int, height: int) -> Image.Image:
    image = source.convert("RGB")
    image.thumbnail((width, height), Image.Resampling.LANCZOS)
    frame = Image.new("RGB", (width, height), "white")
    x = (width - image.width) // 2
    y = (height - image.height) // 2
    frame.paste(image, (x, y))
    return frame


def load_spec(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        spec = json.load(handle)
    if not isinstance(spec, dict) or not isinstance(spec.get("sections"), list):
        raise ValueError("Spec must be an object with a sections array.")
    if not spec["sections"]:
        raise ValueError("Spec sections cannot be empty.")
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path, help="UTF-8 review JSON")
    parser.add_argument("--output", required=True, type=Path, help="Desired PNG path")
    parser.add_argument("--font", help="Optional CJK font path")
    parser.add_argument("--canvas-width", type=int, default=1400)
    parser.add_argument("--image-width", type=int, default=1280)
    args = parser.parse_args()

    spec_path = args.spec.expanduser().resolve()
    if not spec_path.is_file():
        raise FileNotFoundError(f"Review spec not found: {spec_path}")
    spec = load_spec(spec_path)
    font_path = choose_font(args.font)

    if args.canvas_width < 800 or args.image_width < 640:
        raise ValueError("Canvas and image widths are too small for a review sheet.")
    if args.image_width >= args.canvas_width:
        raise ValueError("image-width must be smaller than canvas-width.")

    image_height = round(args.image_width * 9 / 16)
    side_margin = (args.canvas_width - args.image_width) // 2
    top_pad = 54
    title_block = 116
    section_header = 100
    caption_height = 58
    block_gap = 34
    section_gap = 54
    bottom_pad = 70

    title_font = ImageFont.truetype(str(font_path), 40)
    section_font = ImageFont.truetype(str(font_path), 31)
    caption_font = ImageFont.truetype(str(font_path), 25)
    meta_font = ImageFont.truetype(str(font_path), 22)

    normalized_sections = []
    total_items = 0
    for section in spec["sections"]:
        if not isinstance(section, dict) or not isinstance(section.get("items"), list):
            raise ValueError("Each section must contain an items array.")
        if not section["items"]:
            raise ValueError("Review sections cannot be empty.")
        items = []
        for item in section["items"]:
            if not isinstance(item, dict) or not item.get("path"):
                raise ValueError("Each review item must contain a path.")
            items.append(
                {
                    "path": resolve_item_path(str(item["path"]), spec_path.parent),
                    "caption": str(item.get("caption", "")),
                }
            )
        normalized_sections.append({"title": str(section.get("title", "")), "items": items})
        total_items += len(items)

    height = top_pad + title_block + bottom_pad
    height += len(normalized_sections) * (section_header + section_gap)
    height += total_items * (caption_height + image_height + block_gap)

    canvas = Image.new("RGB", (args.canvas_width, height), "white")
    draw = ImageDraw.Draw(canvas)
    y = top_pad

    draw.text((side_margin, y), str(spec.get("title", "文章配图审片长截图")), font=title_font, fill="#202124")
    draw.text((side_margin, y + 58), str(spec.get("subtitle", "")), font=meta_font, fill="#6B7280")
    draw.rounded_rectangle((side_margin, y + 92, side_margin + 210, y + 100), radius=4, fill="#D79B54")
    y += title_block

    for section in normalized_sections:
        y += section_gap
        draw.rounded_rectangle(
            (side_margin, y, args.canvas_width - side_margin, y + 68),
            radius=12,
            fill="#F4F1EC",
        )
        draw.text((side_margin + 24, y + 16), section["title"], font=section_font, fill="#202124")
        y += section_header

        for item in section["items"]:
            draw.text((side_margin + 4, y + 8), item["caption"], font=caption_font, fill="#4B5563")
            y += caption_height
            with Image.open(item["path"]) as source:
                frame = fit_on_white(source, args.image_width, image_height)
            canvas.paste(frame, (side_margin, y))
            draw.rounded_rectangle(
                (side_margin, y, side_margin + args.image_width - 1, y + image_height - 1),
                radius=4,
                outline="#E5E7EB",
                width=2,
            )
            y += image_height + block_gap

    output = next_available(args.output.expanduser().resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.crop((0, 0, args.canvas_width, y + bottom_pad)).save(output, format="PNG", optimize=True)
    print(output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
