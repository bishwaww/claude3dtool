"""
Apply the studio logo everywhere it is used.

  1. Drop your logo (square PNG, ideally 1024x1024, transparent background OK) at
         desktop/assets/logo.png
  2. Run:  backend\\.venv\\Scripts\\python.exe scripts\\apply_logo.py

It writes:
  desktop/assets/icon.ico      Windows .exe / installer / taskbar icon (16–256 px)
  desktop/assets/icon.png      window + splash icon (512 px)
  frontend/public/logo.png     sidebar / titlebar logo (256 px)
  frontend/public/favicon.png  browser tab icon (64 px)
and removes desktop/assets/logo.placeholder, so the backend also prints your logo on the
diegetic STICK KNOWLEDGE brand textures (T-shirt, can label, phone screen…).

  python scripts/apply_logo.py --placeholder   # (re)create the built-in placeholder logo
"""
from __future__ import annotations

import argparse
import hashlib
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "desktop" / "assets"
LOGO = ASSETS / "logo.png"
MARKER = ASSETS / "logo.placeholder"
PUBLIC = ROOT / "frontend" / "public"


def make_placeholder() -> None:
    """Cyan studio-glow tile with a bold white 'SK' and a stick-figure mark."""
    S = 1024
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bg = Image.new("RGBA", (S, S))
    px = bg.load()
    for y in range(S):
        for x in range(S):
            d = min(1.0, math.hypot((x - S * 0.5) / (S * 0.62), (y - S * 0.42) / (S * 0.62)))
            t = d * d * (3 - 2 * d)
            px[x, y] = (int(0x9B + (0x31 - 0x9B) * t), int(0xDA + (0xB9 - 0xDA) * t), int(0xF0 + (0xE6 - 0xF0) * t), 255)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=220, fill=255)
    img.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # stick figure (head + body + arms) in dark ink
    ink = (22, 30, 44, 255)
    cx, top, w = S // 2, 120, 30
    d.ellipse([cx - 55, top, cx + 55, top + 110], fill=ink)                       # head
    neck, hip = top + 135, top + 300
    d.line([(cx, neck), (cx, hip)], fill=ink, width=w)                           # body
    d.line([(cx - 130, neck - 40), (cx, neck + 40), (cx + 130, neck - 40)], fill=ink, width=w, joint="curve")  # arms up
    d.line([(cx - 95, hip + 130), (cx, hip), (cx + 95, hip + 130)], fill=ink, width=w, joint="curve")          # legs
    for x, y in ((cx - 130, neck - 40), (cx + 130, neck - 40), (cx - 95, hip + 130), (cx + 95, hip + 130), (cx, hip)):
        d.ellipse([x - w // 2, y - w // 2, x + w // 2, y + w // 2], fill=ink)   # round line caps
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\seguibl.ttf", 330)
    except OSError:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 330)
    text = "SK"
    b = d.textbbox((0, 0), text, font=font)
    tx, ty = (S - (b[2] - b[0])) // 2 - b[0], 600 - b[1]
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((tx + 10, ty + 14), text, font=font, fill=(0, 40, 70, 120))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(12)))
    d.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))
    d.ellipse([S - 230, S - 230, S - 150, S - 150], fill=(217, 119, 87, 255))  # accent dot
    ASSETS.mkdir(parents=True, exist_ok=True)
    img.save(LOGO)
    MARKER.write_text(hashlib.sha1(LOGO.read_bytes()).hexdigest(), encoding="utf-8")
    print(f"Placeholder logo written to {LOGO}")


def square(img: Image.Image) -> Image.Image:
    img = img.convert("RGBA")
    w, h = img.size
    s = max(w, h)
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    canvas.paste(img, ((s - w) // 2, (s - h) // 2))
    return canvas


def apply() -> None:
    if not LOGO.is_file():
        sys.exit(f"Put your logo at {LOGO} first (or run with --placeholder).")
    src = square(Image.open(LOGO))
    if src.width < 256:
        print("Warning: the logo is smaller than 256 px; icons will look soft.")
    ASSETS.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    big = src.resize((1024, 1024), Image.LANCZOS) if src.width != 1024 else src
    big.resize((512, 512), Image.LANCZOS).save(ASSETS / "icon.png")
    big.save(ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.resize((256, 256), Image.LANCZOS).save(PUBLIC / "logo.png")
    big.resize((64, 64), Image.LANCZOS).save(PUBLIC / "favicon.png")

    digest = hashlib.sha1(LOGO.read_bytes()).hexdigest()
    if MARKER.is_file() and MARKER.read_text(encoding="utf-8").strip() != digest:
        MARKER.unlink()
        print("Custom logo detected: it will also be printed on the diegetic brand textures.")
    elif MARKER.is_file():
        print("Using the placeholder logo (brand textures keep the plain STICK KNOWLEDGE wordmark).")
    for p in (ASSETS / "icon.ico", ASSETS / "icon.png", PUBLIC / "logo.png", PUBLIC / "favicon.png"):
        print("  wrote", p.relative_to(ROOT))
    print("Rebuild the UI (npm run build in frontend/) or the .exe (build_exe.bat) to see it everywhere.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--placeholder", action="store_true", help="create the built-in placeholder logo first")
    a = ap.parse_args()
    if a.placeholder:
        make_placeholder()
    apply()
