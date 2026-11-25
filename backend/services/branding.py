"""
Diegetic branding textures for Blender (Blender's bundled Python has no Pillow, so the
backend renders them). Written to <project>/assets/branding/:

  tshirt.png        transparent chest print (white type, for dark/coloured shirts)
  tshirt_dark.png   transparent chest print (black type, for white shirts — ZDF style)
  prop_wrap.png     sticker / label with border
  screen_ui.png     small UI card for screens
  can_label.png     full wrap-around can label (U = around the can)
  phone_screen.png  9:16 Shorts screen with @stickknowledge (meta-loop ending)
  logo.png          the user's logo, if one was provided

If the user supplies a logo (desktop/assets/logo.png or assets/custom/logo.png), it is
placed on every texture next to the wordmark.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import BRAND_LOGO_CANDIDATES, CUSTOM_LIBRARY_DIR

BRAND_TEXT = "STICK KNOWLEDGE"
BRAND_HANDLE = "@stickknowledge"

_FONTS_BOLD = [
    r"C:\Windows\Fonts\seguibl.ttf",   # Segoe UI Black
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
]
_FONTS_REG = [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"]


def _font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    for f in (_FONTS_BOLD if bold else _FONTS_REG):
        if os.path.isfile(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def find_user_logo(project_assets: Optional[Path] = None) -> Optional[Path]:
    cands = []
    if project_assets:
        cands += [project_assets / "custom" / "logo.png", project_assets / "branding" / "logo_source.png"]
    # The app logo (scripts/apply_logo.py) — unless it is still the shipped placeholder.
    for app_logo in BRAND_LOGO_CANDIDATES:
        if app_logo.is_file() and not (app_logo.parent / "logo.placeholder").exists():
            cands.append(app_logo)
    cands.append(CUSTOM_LIBRARY_DIR / "logo.png")
    return next((c for c in cands if c.is_file()), None)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_w: int, start: int, bold: bool = True):
    size = start
    while size > 12:
        f = _font(size, bold)
        b = draw.textbbox((0, 0), text, font=f)
        if b[2] - b[0] <= max_w:
            return f, b
        size -= 4
    f = _font(12, bold)
    return f, draw.textbbox((0, 0), text, font=f)


def _paste_logo(img: Image.Image, logo: Optional[Image.Image], box: tuple[int, int, int, int]) -> None:
    if logo is None:
        return
    x0, y0, x1, y1 = box
    lg = logo.copy()
    lg.thumbnail((x1 - x0, y1 - y0), Image.LANCZOS)
    img.alpha_composite(lg, (x0 + (x1 - x0 - lg.width) // 2, y0 + (y1 - y0 - lg.height) // 2))


def _wordmark(w: int, h: int, fg, logo: Optional[Image.Image], two_line: bool = True) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lines = ["STICK", "KNOWLEDGE"] if two_line else [BRAND_TEXT]
    text_x0 = 0
    if logo is not None:
        _paste_logo(img, logo, (0, int(h * 0.1), int(h * 0.8), int(h * 0.9)))
        text_x0 = int(h * 0.85)
    avail = w - text_x0
    line_h = h // len(lines)
    for i, ln in enumerate(lines):
        f, b = _fit_text(d, ln, int(avail * 0.96), int(line_h * 0.9))
        tw, th = b[2] - b[0], b[3] - b[1]
        d.text((text_x0 + (avail - tw) // 2 - b[0], i * line_h + (line_h - th) // 2 - b[1]), ln, font=f, fill=fg)
    return img


def prepare_branding_assets(assets_dir: Path, logo_path: Optional[Path] = None, force: bool = False) -> dict[str, str]:
    out_dir = Path(assets_dir) / "branding"
    out_dir.mkdir(parents=True, exist_ok=True)
    logo_path = logo_path or find_user_logo(Path(assets_dir))
    logo = Image.open(logo_path).convert("RGBA") if logo_path and Path(logo_path).is_file() else None
    stamp = out_dir / ".source"
    sig = f"{logo_path}:{Path(logo_path).stat().st_mtime if logo_path else 0}:v2"
    if not force and stamp.is_file() and stamp.read_text() == sig and (out_dir / "phone_screen.png").is_file():
        return {p.stem: str(p) for p in out_dir.glob("*.png")}

    paths: dict[str, str] = {}

    def save(name: str, img: Image.Image) -> None:
        p = out_dir / f"{name}.png"
        img.save(p, "PNG")
        paths[name] = str(p)

    # T-shirt prints (ZDF prints the wordmark big, two lines, on the chest)
    save("tshirt", _wordmark(1024, 620, (255, 255, 255, 255), logo))
    save("tshirt_dark", _wordmark(1024, 620, (20, 20, 22, 255), logo))

    # Sticker / label
    lab = Image.new("RGBA", (1024, 400), (0, 0, 0, 0))
    ImageDraw.Draw(lab).rounded_rectangle([10, 10, 1014, 390], 46, fill=(248, 248, 250, 255), outline=(20, 24, 32, 255), width=10)
    lab.alpha_composite(_wordmark(880, 300, (18, 22, 30, 255), logo), (72, 50))
    save("prop_wrap", lab)

    # Screen UI card
    ui = Image.new("RGBA", (1024, 400), (0, 0, 0, 0))
    ImageDraw.Draw(ui).rounded_rectangle([8, 8, 1016, 392], 40, fill=(12, 20, 36, 250), outline=(56, 189, 248, 255), width=8)
    ui.alpha_composite(_wordmark(860, 290, (255, 255, 255, 255), logo), (82, 55))
    save("screen_ui", ui)

    # Can label: 2048 x 1024 wrap (U around). Blue body with a white band + vertical wordmark,
    # repeated twice so it reads from any angle.
    can = Image.new("RGBA", (2048, 1024), (24, 110, 214, 255))
    cd = ImageDraw.Draw(can)
    for x in range(2048):  # soft vertical sheen
        a = int(40 * (0.5 + 0.5 * __import__("math").cos(x / 2048 * 4 * 3.14159)))
        cd.line([(x, 0), (x, 1023)], fill=(255, 255, 255, a))
    for cx in (512, 1536):
        cd.rounded_rectangle([cx - 230, 140, cx + 230, 884], 60, fill=(250, 250, 252, 255))
        mark = _wordmark(700, 380, (24, 110, 214, 255), logo).rotate(90, expand=True)
        can.alpha_composite(mark, (cx - mark.width // 2, 512 - mark.height // 2))
    save("can_label", can)

    # Phone Shorts screen 1080x1920
    ph = Image.new("RGBA", (1080, 1920), (8, 10, 14, 255))
    pd = ImageDraw.Draw(ph)
    for y in range(1920):  # cyan studio look in the "video" area
        t = y / 1920
        pd.line([(0, y), (1079, y)], fill=(int(49 + 100 * (1 - abs(t - 0.45) * 2)), int(185 + 30 * (1 - abs(t - 0.45) * 2)), 230, 255))
    pd.rectangle([0, 0, 1079, 140], fill=(0, 0, 0, 90))
    f_hdr = _font(54)
    pd.text((60, 40), "Shorts", font=f_hdr, fill=(255, 255, 255, 255))
    big = _wordmark(900, 520, (255, 255, 255, 255), logo)
    shadow = Image.new("RGBA", big.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 150), mask=big.split()[3])
    ph.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)), (96, 706))
    ph.alpha_composite(big, (90, 700))
    for i, label in enumerate(["♥", "…", "↗"]):
        cy = 1180 + i * 170
        pd.ellipse([930, cy, 1040, cy + 110], fill=(0, 0, 0, 110))
        f_ic = _font(56)
        pd.text((985, cy + 55), label, font=f_ic, fill=(255, 255, 255, 255), anchor="mm")
    pd.ellipse([50, 1660, 140, 1750], fill=(255, 255, 255, 255))
    if logo is not None:
        _paste_logo(ph, logo, (56, 1666, 134, 1744))
    pd.text((165, 1675), BRAND_HANDLE, font=_font(46), fill=(255, 255, 255, 255))
    pd.rounded_rectangle([600, 1672, 800, 1740], 34, fill=(255, 255, 255, 255))
    pd.text((700, 1706), "Subscribe", font=_font(32), fill=(0, 0, 0, 255), anchor="mm")
    pd.rectangle([0, 1880, 1079, 1888], fill=(255, 255, 255, 80))
    pd.rectangle([0, 1880, 640, 1888], fill=(255, 0, 0, 255))
    save("phone_screen", ph.convert("RGB").convert("RGBA"))

    if logo is not None:
        save("logo", logo)
    stamp.write_text(sig)
    return paths
