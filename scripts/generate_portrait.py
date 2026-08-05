#!/usr/bin/env python3
"""
generate_portrait.py — turns a headshot into a self-typing ASCII portrait SVG.

Run LOCALLY (not in CI — this needs rembg/onnxruntime, which is a heavy,
non-deterministic-download dependency you don't want in a nightly workflow).

Usage:
    python3 scripts/generate_portrait.py --input photo.jpg --output portrait.svg

Photo requirements (from the guide — a bad photo cannot be rescued by tuning):
    - Side light, ~45 degrees. One side of the face lit, the other in shadow.
    - Fill the frame: crop chin to just above the hair.
    - 1200px+ resolution. Thin features (glasses) get averaged away below that.
    - Plain background. Don't wear black against a dark wall.
    - Slight angle, not dead-on — gives the nose/jaw a shadow edge.
"""

import argparse
import io

import cv2
import numpy as np
from PIL import Image

# The 13-character brightness ramp, darkest to lightest.
# The leading space is deliberate — it's what lets the background
# (post rembg cutout, forced to white) disappear into nothing.
RAMP = " .`:-=+*cs#%@"

# Baked-in advance width assumption — see the README "trap" section.
# JetBrains Mono / Liberation Mono / DejaVu Sans Mono / Noto Sans Mono
# all give 0.600em at this font-size. Consolas (Windows default) does not,
# which is exactly why Part 4 (font embedding) exists.
FONT_SIZE = 12.9
CHAR_W = 7.74


def remove_background(img: Image.Image) -> Image.Image:
    """Cut out the subject, force everything else to white.

    White maps to the blank end of the ramp — skip this step and the
    background fills with '@' and drowns the portrait.
    """
    from rembg import remove

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    cut = remove(buf.getvalue())
    cut_img = Image.open(io.BytesIO(cut)).convert("RGBA")

    white_bg = Image.new("RGBA", cut_img.size, (255, 255, 255, 255))
    composited = Image.alpha_composite(white_bg, cut_img)
    return composited.convert("RGB")


def enhance_contrast(cv_img: np.ndarray) -> np.ndarray:
    """Bilateral filter (smooth skin, keep edges) + CLAHE (local contrast)."""
    smoothed = cv2.bilateralFilter(cv_img, d=9, sigmaColor=75, sigmaSpace=75)
    gray = cv2.cvtColor(smoothed, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def apply_darkening_curve(gray: np.ndarray) -> np.ndarray:
    """(v/255)^1.7 — the fix. Without this the face renders washed out
    and featureless; this is what makes glasses/brows/lips survive.
    """
    normalized = gray.astype(np.float64) / 255.0
    curved = np.power(normalized, 1.7)
    return (curved * 255).astype(np.uint8)


def to_ascii_grid(gray: np.ndarray, cols: int = 90) -> list[str]:
    """Downsample to a character grid and map brightness -> ramp char.

    Rows = cols * (h/w) * 0.48, because monospace characters are about
    twice as tall as they are wide.
    """
    h, w = gray.shape
    rows = max(1, round(cols * (h / w) * 0.48))

    resized = cv2.resize(gray, (cols, rows), interpolation=cv2.INTER_AREA)

    ramp_len = len(RAMP) - 1
    lines = []
    for r in range(rows):
        line_chars = []
        for c in range(cols):
            brightness = resized[r, c] / 255.0
            # Dark pixels -> dense characters (@), light pixels -> blank space.
            # RAMP goes light-to-heavy (" " ... "@"), so index by *darkness*.
            idx = min(ramp_len, int((1.0 - brightness) * ramp_len))
            line_chars.append(RAMP[idx])
        lines.append("".join(line_chars))
    return lines


def build_svg(lines: list[str], display_width: int = 460, embed_font_path: str | None = None) -> str:
    """Each row sits in a clipPath whose rect animates width 0 -> full,
    with a small block riding the wipe edge as a cursor. Rows stagger
    top to bottom. fill="freeze" so it prints once and stops — no loop.
    """
    cols = max(len(l) for l in lines)
    rows = len(lines)

    svg_w = cols * CHAR_W
    svg_h = rows * FONT_SIZE * 1.0
    scale = display_width / svg_w

    font_face = ""
    if embed_font_path:
        import base64

        with open(embed_font_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        font_face = f"""
    <style>
      @font-face {{
        font-family: 'RampFont';
        src: url(data:font/woff2;base64,{b64}) format('woff2');
      }}
      text {{ font-family: 'RampFont', monospace; }}
    </style>"""

    parts = [
        f'<svg viewBox="0 0 {svg_w:.1f} {svg_h:.1f}" '
        f'width="{display_width}" height="{svg_h * scale:.1f}" '
        f'xmlns="http://www.w3.org/2000/svg">',
        font_face,
    ]

    for i, line in enumerate(lines):
        y = (i + 1) * FONT_SIZE
        begin = f"{i * 0.09:.2f}s"
        line_w = len(line) * CHAR_W
        escaped = (
            line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

        parts.append(f"""
    <clipPath id="clip{i}">
      <rect x="0" y="{y - FONT_SIZE:.1f}" width="0" height="{FONT_SIZE:.1f}">
        <animate attributeName="width" from="0" to="{line_w:.1f}"
                 begin="{begin}" dur="0.35s" fill="freeze" />
      </rect>
    </clipPath>
    <text x="0" y="{y:.1f}" font-size="{FONT_SIZE}" fill="currentColor"
          xml:space="preserve" clip-path="url(#clip{i})">{escaped}</text>
    <rect x="0" y="{y - FONT_SIZE:.1f}" width="{CHAR_W:.2f}" height="{FONT_SIZE:.1f}"
          fill="currentColor" opacity="0.6">
      <animate attributeName="x" from="0" to="{line_w:.1f}"
               begin="{begin}" dur="0.35s" fill="freeze" />
      <set attributeName="opacity" to="0" begin="{i * 0.09 + 0.35:.2f}s" fill="freeze" />
    </rect>""")

    parts.append("\n</svg>")
    return "".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="path to headshot photo")
    ap.add_argument("--output", default="portrait.svg")
    ap.add_argument("--cols", type=int, default=90)
    ap.add_argument("--display-width", type=int, default=460)
    ap.add_argument(
        "--font",
        default=None,
        help="path to a subsetted .woff2 (see fonts/SUBSET_INSTRUCTIONS.md) "
        "to embed, fixing the Windows/Consolas 7%% narrower issue",
    )
    args = ap.parse_args()

    img = Image.open(args.input).convert("RGB")
    print("Removing background...")
    cutout = remove_background(img)

    cv_img = cv2.cvtColor(np.array(cutout), cv2.COLOR_RGB2BGR)
    print("Enhancing contrast (bilateral filter + CLAHE)...")
    gray = enhance_contrast(cv_img)

    print("Applying darkening curve...")
    curved = apply_darkening_curve(gray)

    print(f"Building {args.cols}-column ASCII grid...")
    lines = to_ascii_grid(curved, cols=args.cols)

    print("Rendering animated SVG...")
    svg = build_svg(lines, display_width=args.display_width, embed_font_path=args.font)

    with open(args.output, "w") as f:
        f.write(svg)

    rows = len(lines)
    approx_duration = rows * 0.09 + 0.35
    print(f"Wrote {args.output} — {rows} rows, ~{approx_duration:.1f}s to finish typing.")
    print("Preview tip: a full-page headless-Chrome screenshot restarts SMIL — "
          "use a tall viewport instead and wait for it to finish.")


if __name__ == "__main__":
    main()
