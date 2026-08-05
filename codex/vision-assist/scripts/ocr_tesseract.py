#!/usr/bin/env python3
"""OCR via Tesseract: cross-platform fallback when PaddleOCR is unavailable.

Usage:
  python ocr_tesseract.py --image <path> [--lang chi_sim]

Requires: tesseract binary + `pip install pytesseract Pillow`.
See references/install.md for per-platform setup.
"""

import argparse
import shutil
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--lang", default="chi_sim")
    args = ap.parse_args()

    if shutil.which("tesseract") is None:
        print("ERROR: tesseract binary not found. Install it (see references/install.md).", file=sys.stderr)
        sys.exit(3)
    try:
        import pytesseract
    except ImportError:
        print("ERROR: pytesseract not installed. Run: pip install pytesseract Pillow", file=sys.stderr)
        sys.exit(3)
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow not installed. Run: pip install Pillow", file=sys.stderr)
        sys.exit(3)

    img = Image.open(args.image)
    data = pytesseract.image_to_data(img, lang=args.lang, output_type=pytesseract.Output.DICT)

    lines = {}
    for i in range(len(data["text"])):
        txt = data["text"][i].strip()
        if not txt:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        box = lines.setdefault(
            key,
            {
                "x": data["left"][i],
                "y": data["top"][i],
                "right": data["left"][i] + data["width"][i],
                "bottom": data["top"][i] + data["height"][i],
                "words": [],
            },
        )
        box["x"] = min(box["x"], data["left"][i])
        box["y"] = min(box["y"], data["top"][i])
        box["right"] = max(box["right"], data["left"][i] + data["width"][i])
        box["bottom"] = max(box["bottom"], data["top"][i] + data["height"][i])
        box["words"].append(txt)

    print("===== OCR result (Tesseract) =====")
    for idx, key in enumerate(sorted(lines.keys()), 1):
        b = lines[key]
        print(f"{idx:3}: ({b['x']},{b['y']},{b['right'] - b['x']},{b['bottom'] - b['y']}) {' '.join(b['words'])}")
    print("===== end =====")


if __name__ == "__main__":
    main()
