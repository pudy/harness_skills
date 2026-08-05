#!/usr/bin/env python3
"""Unified entry point for the vision-assist skill.

One command for the whole pipeline:
  * provider guard (only run for text-only models)
  * free vision API first (Zhipu GLM free models ONLY; paid providers are
    out of scope for this skill by design)
  * automatic fallback to local OCR (Windows built-in / PaddleOCR / Tesseract)
    when the API is rate-limited or unreachable

Usage:
  python vision.py --check
  python vision.py --image <path>
  python vision.py --url <http(s) url>          # image or PDF (public URL)
  python vision.py --image <file.pdf>           # PDF: render pages, then API/OCR
  python vision.py --image <path> [--region x,y,w,h] [--scale 2] [--grayscale]
  python vision.py --image <path> --mode ocr
  python vision.py --image <path> --mode api [--compact] [--prompt "..."]
  python vision.py --latest [--mode auto|ocr|api]

Exit codes:
  0  success
  1  disabled for current model / image not found / recover failed / API failed
  2  no OCR engine available
  3  API requested but no key configured
"""

import argparse
import contextlib
import io
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

try:
    from describe_with_image import MODEL_SUPPORTS_FILES
except ImportError:  # pragma: no cover - keep a safe fallback
    MODEL_SUPPORTS_FILES = {"glm-4.6v-flash", "glm-4.1v-thinking-flash"}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.environ.get("VISION_CONFIG") or os.path.join(os.path.dirname(SCRIPT_DIR), "config.json")
CONFIG_TOML = os.environ.get("VISION_CONFIG_TOML") or os.path.join(os.path.expanduser("~"), ".codex", "config.toml")
DEFAULT_ALLOWED = ["deepseek-v4-flash", "deepseek-v4-pro"]


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def get_current_model():
    try:
        with open(CONFIG_TOML, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
    except OSError:
        return None
    m = re.search(r"^\s*model\s*=\s*[\"']([^\"']+)[\"']", text, re.M)
    return m.group(1) if m else None


def allowed_models():
    env = os.environ.get("VISION_ALLOWED_MODELS")
    if env:
        return [s.strip() for s in env.split(",") if s.strip()]
    cfg = load_config()
    if isinstance(cfg.get("allowed_models"), list) and cfg["allowed_models"]:
        return cfg["allowed_models"]
    return DEFAULT_ALLOWED


def provider_guard():
    model = get_current_model()
    allowed = allowed_models()
    if model in allowed:
        return
    sys.stderr.write(
        f"ERROR: vision-assist is disabled for the current model "
        f"({model or 'unknown'}); it only runs for text-only models: {', '.join(allowed)}. "
        f"Models with native vision should not use this skill.\n"
    )
    sys.exit(1)


def engine_status():
    sys_platform = platform.system().lower()
    paddle = importlib.util.find_spec("paddleocr") is not None
    tesseract = shutil.which("tesseract") is not None
    win_ocr = sys_platform == "windows"
    return sys_platform, paddle, tesseract, win_ocr


def pick_engine():
    sys_platform, paddle, tesseract, win_ocr = engine_status()
    if paddle:
        return "paddle", os.path.join(SCRIPT_DIR, "ocr_paddle.py")
    if win_ocr:
        return "windows", os.path.join(SCRIPT_DIR, "ocr.ps1")
    if tesseract:
        return "tesseract", os.path.join(SCRIPT_DIR, "ocr_tesseract.py")
    return None, None


def run_windows_ocr(image, region, scale, grayscale):
    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", os.path.join(SCRIPT_DIR, "ocr.ps1"),
        "-Path", image,
    ]
    if region:
        cmd += ["-Region", region]
    if scale and scale > 1:
        cmd += ["-Scale", str(scale)]
    if grayscale:
        cmd += ["-Grayscale"]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def run_python_ocr(script, image):
    return subprocess.run(
        [sys.executable, script, "--image", image],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def run_ocr(image, region, scale, grayscale):
    engine, script = pick_engine()
    if not engine:
        return None, None, "no engine"
    if engine == "windows":
        proc = run_windows_ocr(image, region, scale, grayscale)
    else:
        proc = run_python_ocr(script, image)
    return engine, proc, None


def has_api_key():
    cfg = load_config()
    key = os.environ.get("VISION_API_KEY") or cfg.get("api_key") or ""
    return bool(key) and key.strip() and "PASTE" not in key.upper()


def is_url(s):
    return bool(s) and (s.startswith("http://") or s.startswith("https://"))


def is_pdf_source(s):
    return bool(s) and s.lower().endswith(".pdf")


def download_to_temp(url, tmpdir):
    """Download a URL to a temp file; extension guessed from URL/content-type."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Codex vision-assist)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
        ctype = resp.headers.get("Content-Type", "") or ""
    name = url.split("/")[-1].split("?")[0].lower()
    if name.endswith(".pdf") or "pdf" in ctype.lower():
        ext = ".pdf"
    elif name.endswith((".jpg", ".jpeg")) or "jpeg" in ctype.lower() or "jpg" in ctype.lower():
        ext = ".jpg"
    elif name.endswith(".png") or "png" in ctype.lower():
        ext = ".png"
    else:
        ext = ".bin"
    path = os.path.join(tmpdir, "download" + ext)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def run_api(image, compact, prompt, model=None, file_input=False):
    if not has_api_key():
        sys.stderr.write(
            "API fallback skipped: no free vision-API key configured.\n"
            "Put your Zhipu key into config.json (see references/install.md); "
            "this skill never uses paid providers.\n"
        )
        return None, 3
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "describe_with_image.py"), "--image", image]
    if model:
        cmd += ["--model", model]
    if file_input:
        cmd.append("--file")
    if compact:
        cmd.append("--compact")
    if prompt:
        cmd += ["--prompt", prompt]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc, proc.returncode


# Retry policy per failure class. Each entry is the list of delays between
# attempts (total attempts = len(delays) + 1). Both classes are currently
# empty: every free model is tried exactly once, then the chain moves to the
# next model. Rate limits are per model, so switching models fixes overload
# faster than waiting on the same one; 401/403 (account-level) stop the chain.
RETRY_POLICY = {
    "rate_limit": [],
    "server": [],
}


def parse_api_error(stderr):
    """Extract (http_status, zhipu_code) from the machine-readable error line."""
    m = re.search(r"\[vision-api-error\]\s+status=(\d+)\s+zhipu_code=(\S+)", stderr or "")
    if not m:
        return None, None
    zc = m.group(2)
    return int(m.group(1)), (None if zc in ("None", "none", "") else zc)


def classify_api_error(stderr):
    """Classify a failure:

    - "rate_limit": HTTP 429 or Zhipu codes 1302/1305 -> next model, no retry
    - "server":     HTTP 5xx / network failure -> next model, no retry
    - "next":       permanent request error (400/404/... ) or too-short reply
                    -> next model, no waiting
    - "stop":       permanent account-level error (401/403) -> abort the chain
    """
    if "vision-api-tooshort" in (stderr or ""):
        return "next"  # HTTP 200 but useless output; retrying usually repeats it
    status, zcode = parse_api_error(stderr)
    if zcode in ("1302", "1305"):
        return "rate_limit"
    if status is None:
        return "server"  # network-level failure; treat as transient
    if status in (401, 403):
        return "stop"
    if status == 429:
        return "rate_limit"
    if 400 <= status < 500:
        return "next"
    return "server"  # 5xx and anything unexpected: transient server issue


def run_api_with_retry(image, compact, prompt, file_input=False):
    """Free API with bounded retries and cross-model failover.

    Order: primary model (config `model`) -> fallback_models (config) ->
    caller falls back to OCR. Every model is tried exactly once; any failure
    moves to the next free model with no same-model retry. Permanent request
    errors jump straight to the next model; permanent account-level errors
    stop the chain immediately (same key, so other models fail the same way).
    With file_input=True (PDF URLs), models without file_url support are skipped.
    """
    cfg = load_config()
    models = [cfg.get("model") or "glm-4.1v-thinking-flash"]
    fb = cfg.get("fallback_models")
    if isinstance(fb, list):
        models += [m for m in fb if isinstance(m, str) and m]
    seen = set()
    models = [m for m in models if not (m in seen or seen.add(m))]
    if file_input:
        models = [m for m in models if m in MODEL_SUPPORTS_FILES]

    proc, code = None, 1
    for model in models:
        attempt = 0
        while True:
            attempt += 1
            proc, code = run_api(image, compact, prompt, model=model, file_input=file_input)
            if proc is None or code == 0:
                return proc, code
            action = classify_api_error(proc.stderr)
            if action == "stop":
                sys.stderr.write(
                    f"[vision-api] {model} permanent account-level error; "
                    "stopping the API chain (falling back to OCR).\n"
                )
                return proc, code
            if action == "next":
                sys.stderr.write(
                    f"[vision-api] {model} permanent request error; "
                    "trying the next free model without waiting...\n"
                )
                break
            delays = RETRY_POLICY[action]
            max_attempts = len(delays) + 1
            if attempt < max_attempts:
                delay = delays[attempt - 1]
                sys.stderr.write(
                    f"[vision-api] {model} transient error ({action}, "
                    f"attempt {attempt}/{max_attempts}); retrying in {delay}s...\n"
                )
                time.sleep(delay)
            else:
                sys.stderr.write(
                    f"[vision-api] {model} failed ({action}); "
                    "trying the next free model...\n"
                )
                break
    return proc, code


def ocr_image_text(image, args):
    """Run local OCR; returns (exit_code, stdout_text, stderr_note)."""
    engine, proc, err = run_ocr(image, args.region, args.scale, args.grayscale)
    if err == "no engine":
        return 2, None, (
            "ERROR: no OCR engine available. See references/install.md "
            "(PaddleOCR / Tesseract per platform).\n"
        )
    if proc.returncode != 0:
        return 1, None, f"OCR engine ({engine}) failed.\n{proc.stderr}"
    return 0, proc.stdout, f"engine: {engine}\n"


def run_image_ocr(image, args):
    code, text, note = ocr_image_text(image, args)
    if text:
        sys.stdout.write(text)
    if note:
        sys.stderr.write(note)
    return code


def process_image(image, args):
    """Single image: API first (auto/api), OCR fallback (auto only)."""
    if args.mode == "api" or has_api_key():
        proc, code = run_api_with_retry(image, args.compact, args.prompt)
        if proc is not None and code == 0:
            sys.stdout.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            return 0
        if args.mode == "api":
            if proc is not None:
                sys.stderr.write(proc.stderr)
            sys.stderr.write("API failed; --mode api has no OCR fallback.\n")
            return code or 1
        if proc is not None:
            sys.stderr.write(proc.stderr)
        sys.stderr.write("API failed; falling back to local OCR.\n")
    return run_image_ocr(image, args)


# Ratio of suspicious chars (broken ToUnicode mapping, e.g. Chrome print-to-PDF)
# above which native extraction is treated as garbage and vision is used.
GARBLED_RATIO_THRESHOLD = 0.10
# Literal '?' can legitimately appear in text (questions, code); only treat it
# as a corruption signal when it dominates the page.
GARBLED_QMARK_THRESHOLD = 0.30


def _is_suspicious_char(ch):
    o = ord(ch)
    if ch == "?" or o == 0xFFFD:
        return True
    if 0xE000 <= o <= 0xF8FF:  # private use area (unmapped glyphs)
        return True
    if 0x2F00 <= o <= 0x2FDF:  # Kangxi radicals (broken ToUnicode mapping)
        return True
    if o < 32 and ch not in "\t\n\r":
        return True
    return False


def garbled_ratio(text):
    if not text:
        return 0.0
    # literal '?' is handled separately so normal question marks don't trip this
    return sum(1 for ch in text if _is_suspicious_char(ch) and ch != "?") / len(text)


def is_garbled_text(text):
    if not text:
        return False
    q_ratio = text.count("?") / len(text)
    return (
        garbled_ratio(text) >= GARBLED_RATIO_THRESHOLD
        or q_ratio >= GARBLED_QMARK_THRESHOLD
    )


def extract_pdf_text(pdf_path, max_pages):
    """Native local text extraction via pdfplumber; returns combined text or None.

    Returns None when there is no text layer OR the extraction is garbled
    (broken ToUnicode mapping), so the caller falls back to rendered pages.
    """
    try:
        import pdfplumber
    except ImportError:
        return None
    try:
        # pdfminer can spam "FontBBox" warnings for broken font descriptors;
        # suppress them - garbled mappings are handled by is_garbled_text().
        with contextlib.redirect_stderr(io.StringIO()):
            with pdfplumber.open(pdf_path) as pdf:
                total = len(pdf.pages)
                raw_pages = []
                for i, page in enumerate(pdf.pages):
                    if i >= max_pages:
                        break
                    raw_pages.append(page.extract_text() or "")
        raw = "\n".join(raw_pages)
        if is_garbled_text(raw):
            sys.stderr.write(
                f"[pdf] native text extraction looks garbled "
                f"({garbled_ratio(raw):.0%} suspicious chars); "
                "falling back to rendered pages.\n"
            )
            return None
        parts = []
        for i, t in enumerate(raw_pages):
            t = t.strip()
            if t:
                parts.append(f"===== PDF page {i + 1}/{min(total, max_pages)} (text) =====\n{t}")
        return "\n\n".join(parts) if parts else None
    except Exception:
        return None


def process_pdf(source, local, tmpdir, args, pdf_max_pages, pdf_dpi):
    """PDF pipeline, local-first:
    1. native text extraction (pdfplumber) - accurate, fast, free
    2. if no extractable text (scanned/image PDF): render pages -> vision API -> OCR
    """
    if args.mode == "auto":
        text = extract_pdf_text(local, pdf_max_pages)
        if text:
            sys.stdout.write(text + "\n")
            sys.stderr.write("engine: pdf native text extraction\n")
            return 0
        sys.stderr.write("no usable native text (scanned or garbled); falling back to rendered pages.\n")

    if importlib.util.find_spec("fitz") is None:
        sys.stderr.write("ERROR: PDF support needs PyMuPDF. Run: pip install PyMuPDF\n")
        return 2

    render = subprocess.run(
        [
            sys.executable, os.path.join(SCRIPT_DIR, "pdf_to_images.py"),
            "--input", local, "--output-dir", tmpdir,
            "--dpi", str(pdf_dpi), "--max-pages", str(pdf_max_pages),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if render.returncode != 0:
        sys.stderr.write(render.stderr)
        return render.returncode
    pages = [p for p in render.stdout.splitlines() if p.strip()]
    if not pages:
        sys.stderr.write("ERROR: no pages rendered.\n")
        return 1

    total = len(pages)
    ok = 0
    for idx, page in enumerate(pages, 1):
        sys.stderr.write(f"--- PDF page {idx}/{total} ---\n")
        if args.mode == "ocr":
            code, text, note = ocr_image_text(page, args)
            if code == 0:
                sys.stdout.write(f"===== PDF page {idx}/{total} (OCR) =====\n")
                sys.stdout.write(text)
                sys.stderr.write(note)
                ok += 1
            else:
                sys.stderr.write(note)
            continue
        proc, code = run_api_with_retry(page, args.compact, args.prompt)
        if proc is not None and code == 0:
            sys.stdout.write(f"===== PDF page {idx}/{total} (vision) =====\n")
            sys.stdout.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            ok += 1
            continue
        if args.mode == "api":
            if proc is not None:
                sys.stderr.write(proc.stderr)
            sys.stderr.write(f"page {idx}: API failed; skipping (--mode api has no OCR fallback).\n")
            continue
        if proc is not None:
            sys.stderr.write(proc.stderr)
        sys.stderr.write(f"page {idx}: API failed; falling back to local OCR.\n")
        code, text, note = ocr_image_text(page, args)
        if code == 0:
            sys.stdout.write(f"===== PDF page {idx}/{total} (OCR) =====\n")
            sys.stdout.write(text)
            sys.stderr.write(note)
            ok += 1
        else:
            sys.stderr.write(note)
            sys.stderr.write(f"page {idx}: all methods failed.\n")
    if ok == 0:
        sys.stderr.write("ERROR: no PDF page could be read.\n")
        return 1
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="print engine/guard/API status and exit")
    ap.add_argument("--image", help="image file to read")
    ap.add_argument("--url", help="http(s) URL of an image or PDF")
    ap.add_argument("--latest", action="store_true", help="recover the most recent pasted image first")
    ap.add_argument("--mode", choices=["auto", "ocr", "api"], default="auto")
    ap.add_argument("--compact", action="store_true", help="focused fact-only output for the API fallback")
    ap.add_argument("--prompt", help="specific question for the API fallback")
    ap.add_argument("--region", help="Windows OCR crop: x,y,width,height")
    ap.add_argument("--scale", type=int, default=0, help="Windows OCR upscale factor (e.g. 2)")
    ap.add_argument("--grayscale", action="store_true", help="Windows OCR grayscale preprocessing")
    args = ap.parse_args()

    if args.check:
        sys_platform, paddle, tesseract, win_ocr = engine_status()
        model = get_current_model()
        print(f"platform: {sys_platform}")
        print(f"current model: {model}")
        print(f"guard active: {'yes' if model in allowed_models() else 'no (skill disabled for this model)'}")
        print(f"paddleocr: {'yes' if paddle else 'no'}")
        print(f"tesseract: {'yes' if tesseract else 'no'}")
        print(f"windows builtin ocr: {'yes' if win_ocr else 'no'}")
        print(f"free vision api key: {'configured' if has_api_key() else 'not configured'}")
        cfg = load_config()
        print(f"api model: {cfg.get('model') or 'glm-4.1v-thinking-flash (default)'}")
        print(f"pdf rendering (PyMuPDF): {'yes' if importlib.util.find_spec('fitz') else 'no'}")
        return 0

    provider_guard()

    source = args.url or args.image
    if args.latest:
        if platform.system().lower() == "windows":
            sys.stderr.write(
                "SKIP: session recovery is not applicable on Windows - the desktop "
                "app blocks image uploads for text-only models. Ask the user for "
                "the file path instead.\n"
            )
            sys.exit(1)
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "recover_pasted_image.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            sys.exit(1)
        source = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else None
        if not source:
            sys.stderr.write("ERROR: recovery returned no image path.\n")
            sys.exit(1)
        sys.stderr.write(f"recovered image: {source}\n")

    if not source:
        sys.stderr.write("ERROR: no image given. Use --image <path>, --url <http(s)>, or --latest.\n")
        sys.exit(1)

    cfg = load_config()
    pdf_max_pages = int(cfg.get("pdf_max_pages") or 20)
    pdf_dpi = int(cfg.get("pdf_dpi") or 150)
    tmpdir = tempfile.mkdtemp(prefix="vision_tmp_")
    try:
        local = source
        if is_url(source):
            sys.stderr.write(f"downloading: {source}\n")
            try:
                local = download_to_temp(source, tmpdir)
            except Exception as exc:
                sys.stderr.write(f"ERROR: download failed: {exc}\n")
                sys.exit(1)
            sys.stderr.write(f"downloaded to: {local}\n")
        elif not os.path.isfile(local):
            sys.stderr.write(f"ERROR: image not found: {local}\n")
            sys.exit(1)

        if is_pdf_source(source) or local.lower().endswith(".pdf"):
            return process_pdf(source, local, tmpdir, args, pdf_max_pages, pdf_dpi)

        if args.mode == "ocr":
            return run_image_ocr(local, args)
        return process_image(local, args)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
