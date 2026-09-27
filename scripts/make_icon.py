#!/usr/bin/env python3
"""Generate a macOS app icon (icns + png) for PokeHunt Controller."""

from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT = Path(__file__).resolve().parent.parent
ASSETS = PROJECT / "assets"
ICONSET = ASSETS / "PokeHunt.iconset"
ICNS = ASSETS / "PokeHunt.icns"


def draw_pokeball(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # macOS-style rounded rect background
    margin = int(size * 0.06)
    radius = int(size * 0.22)
    bg = (15, 17, 21, 255)  # #0F1115
    draw.rounded_rectangle([margin, margin, size - margin, size - margin], radius=radius, fill=bg)

    # Subtle border
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        outline=(46, 53, 72, 255),
        width=max(1, size // 128),
    )

    cx = cy = size // 2
    ball_r = int(size * 0.32)

    # Ball body
    top = (237, 66, 69, 255)       # red
    bottom = (242, 244, 248, 255)  # white
    band = (24, 26, 32, 255)

    # Top half
    draw.pieslice(
        [cx - ball_r, cy - ball_r, cx + ball_r, cy + ball_r],
        start=180, end=360, fill=top,
    )
    # Bottom half
    draw.pieslice(
        [cx - ball_r, cy - ball_r, cx + ball_r, cy + ball_r],
        start=0, end=180, fill=bottom,
    )
    # Center band
    band_h = max(2, size // 36)
    draw.rectangle([cx - ball_r, cy - band_h // 2, cx + ball_r, cy + band_h // 2], fill=band)
    # Outer ring
    draw.ellipse(
        [cx - ball_r, cy - ball_r, cx + ball_r, cy + ball_r],
        outline=band,
        width=max(2, size // 48),
    )
    # Center button
    btn_outer = int(ball_r * 0.38)
    btn_inner = int(ball_r * 0.22)
    draw.ellipse(
        [cx - btn_outer, cy - btn_outer, cx + btn_outer, cy + btn_outer],
        fill=band,
    )
    draw.ellipse(
        [cx - btn_inner, cy - btn_inner, cx + btn_inner, cy + btn_inner],
        fill=bottom,
        outline=(180, 185, 195, 255),
        width=max(1, size // 200),
    )

    # Gold accent sparkle (top-left of ball)
    sparkle = int(size * 0.04)
    sx, sy = int(cx - ball_r * 0.45), int(cy - ball_r * 0.45)
    draw.ellipse([sx - sparkle, sy - sparkle, sx + sparkle, sy + sparkle], fill=(255, 203, 5, 200))

    return img


def main() -> int:
    ASSETS.mkdir(exist_ok=True)
    if ICONSET.exists():
        for p in ICONSET.iterdir():
            p.unlink()
    else:
        ICONSET.mkdir()

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for s in sizes:
        img = draw_pokeball(s)
        img.save(ICONSET / f"icon_{s}x{s}.png")
        if s * 2 <= 1024:
            img_2x = draw_pokeball(s * 2)
            img_2x.save(ICONSET / f"icon_{s}x{s}@2x.png")

    # Also save a standalone preview png
    preview = draw_pokeball(512)
    preview.save(ASSETS / "PokeHunt-icon.png")

    # Build .icns via iconutil (macOS)
    if ICNS.exists():
        ICNS.unlink()
    result = subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("iconutil failed:", result.stderr, file=sys.stderr)
        # Fallback: write a minimal ICNS with PNG data for 512
        png_path = ICONSET / "icon_512x512.png"
        data = png_path.read_bytes()
        # Very small icns wrapper: header + ic07 (PNG 512)
        # icns format: 'icns' + total size + type + size + data
        def chunk(tag: bytes, payload: bytes) -> bytes:
            return tag + struct.pack(">I", 8 + len(payload)) + payload

        body = chunk(b"ic07", data) + chunk(b"ic08", (ICONSET / "icon_256x256.png").read_bytes())
        total = 8 + len(body)
        ICNS.write_bytes(b"icns" + struct.pack(">I", total) + body)
        print(f"Wrote fallback {ICNS}")
    else:
        print(f"Wrote {ICNS}")
    print(f"Preview: {ASSETS / 'PokeHunt-icon.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
