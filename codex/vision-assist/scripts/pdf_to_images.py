#!/usr/bin/env python3
"""Render PDF pages to PNG images for the vision pipeline.

Requires PyMuPDF (pip install PyMuPDF). Cross-platform.

Usage:
  python pdf_to_images.py --input <file.pdf> --output-dir <dir> [--dpi 150] [--max-pages 20]

Prints one rendered page path per line on stdout.
"""

import argparse
import os
import sys


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="PDF file path")
    ap.add_argument("--output-dir", required=True, help="directory for rendered PNG pages")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--max-pages", type=int, default=20)
    args = ap.parse_args()

    try:
        import fitz
    except ImportError:
        print(
            "ERROR: PyMuPDF is not installed. Run: pip install PyMuPDF",
            file=sys.stderr,
        )
        sys.exit(2)

    if not os.path.isfile(args.input):
        print(f"ERROR: PDF not found: {args.input}", file=sys.stderr)
        sys.exit(2)

    os.makedirs(args.output_dir, exist_ok=True)
    try:
        doc = fitz.open(args.input)
    except Exception as exc:
        print(f"ERROR: cannot open PDF: {exc}", file=sys.stderr)
        sys.exit(1)

    if doc.page_count == 0:
        print("ERROR: PDF has no pages", file=sys.stderr)
        sys.exit(1)

    pages = min(doc.page_count, args.max_pages)
    scale = args.dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    out_paths = []
    try:
        for i in range(pages):
            pix = doc[i].get_pixmap(matrix=mat)
            out = os.path.join(args.output_dir, f"page_{i + 1:03d}.png")
            pix.save(out)
            out_paths.append(out)
    finally:
        doc.close()

    for p in out_paths:
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
