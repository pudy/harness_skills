#!/usr/bin/env python3
"""One-time static check: which OCR engines are available on this machine?

Run once per thread when the skill first triggers. Output is tiny (a few lines).
"""

import importlib.util
import platform
import shutil


def main():
    sys_platform = platform.system().lower()  # windows / linux / darwin
    paddle = importlib.util.find_spec("paddleocr") is not None
    tesseract = shutil.which("tesseract") is not None
    print("platform:", sys_platform)
    print("paddleocr:", "yes" if paddle else "no")
    print("tesseract:", "yes" if tesseract else "no")
    print("windows_builtin_ocr:", "yes" if sys_platform == "windows" else "no")
    if sys_platform != "windows" and not paddle and not tesseract:
        print("NOTE: no OCR engine installed on this non-Windows machine. "
              "See references/install.md and remind the user.")


if __name__ == "__main__":
    main()
