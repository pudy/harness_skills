#!/usr/bin/env python3
"""Optional OCR with PaddleOCR (better Chinese recognition than Windows OCR).

Usage:
  python ocr_paddle.py --image <path> [--lang ch]

Requires: pip install paddleocr paddlepaddle
Fall back to scripts/ocr.ps1 when PaddleOCR is not installed.
"""

import argparse
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--lang", default="ch")
    args = ap.parse_args()

    try:
        from paddleocr import PaddleOCR
    except ImportError:
        print("ERROR: PaddleOCR is not installed.", file=sys.stderr)
        print("Install it with: pip install paddleocr paddlepaddle", file=sys.stderr)
        print("See references/install.md for per-platform notes.", file=sys.stderr)
        sys.exit(3)

    ocr = PaddleOCR(use_angle_cls=True, lang=args.lang, show_log=False)
    result = ocr.ocr(args.image, cls=True)
    lines = result[0] if result else None
    if not lines:
        print("===== OCR result =====")
        print("(no text found)")
        return

    print("===== OCR result (PaddleOCR) =====")
    for idx, item in enumerate(lines, 1):
        box, text_info = item
        text, conf = text_info
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x, y = int(min(xs)), int(min(ys))
        w, h = int(max(xs) - min(xs)), int(max(ys) - min(ys))
        print(f"{idx:3}: ({x},{y},{w},{h}) {text} (conf {conf:.2f})")
    print("===== end =====")


if __name__ == "__main__":
    main()
