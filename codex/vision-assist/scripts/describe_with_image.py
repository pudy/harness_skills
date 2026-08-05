#!/usr/bin/env python3
"""Send an image to a FREE OpenAI-compatible vision API and print the text reply.

Default provider: Zhipu (bigmodel.cn) free models, e.g. glm-4.1v-thinking-flash.
This skill is deliberately limited to free providers; paid providers are
handled by a separate skill and must never be configured here.

Config sources (first match wins):
  - env VISION_API_KEY / VISION_API_MODEL / VISION_API_ENDPOINT / VISION_TIMEOUT_MS
    / VISION_MIN_REPLY_CHARS
  - config.json next to the skill (see config.json.example)

Usage:
  python describe_with_image.py --image <path-or-url> [--compact] [--prompt "..."]
  python describe_with_image.py --image <pdf-url> --file [--compact] [--prompt "..."]
"""

import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.environ.get("VISION_CONFIG") or os.path.join(os.path.dirname(SCRIPT_DIR), "config.json")

DEFAULT_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-4.1v-thinking-flash"
DEFAULT_TIMEOUT_MS = 60000
DEFAULT_MAX_TOKENS = 4000
DEFAULT_MIN_REPLY_CHARS = 10
MODEL_MAX_TOKENS = {
    "glm-4v-flash": 1024,
    "glm-4.6v-flash": 32000,
    "glm-4.1v-thinking-flash": 16384,
}

# Models that accept file_url (PDF/document) input; glm-4v-flash is image-only.
MODEL_SUPPORTS_FILES = {"glm-4.6v-flash", "glm-4.1v-thinking-flash"}

FULL_PROMPT = (
    "Describe this image in detail: all visible text (quote it exactly), "
    "UI elements, layout, and any numbers."
)
COMPACT_PROMPT = (
    "Extract ONLY the facts from this image: exact visible text, key numbers, "
    "error messages, and element names. Do not analyze, suggest, or add pleasantries."
)


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def is_url(s):
    return bool(s) and (s.startswith("http://") or s.startswith("https://"))


def build_payload(image, model, prompt, max_tokens, as_file=False):
    """Build the chat payload.

    - Public URL image -> image_url with the URL directly.
    - Local image       -> base64 data URL (image_url).
    - Public URL PDF    -> file_url (only models with file support).
    - Local PDF         -> not supported here; render to images first.
    """
    if is_url(image):
        if as_file:
            content = [
                {"type": "text", "text": prompt},
                {"type": "file_url", "file_url": {"url": image}},
            ]
        else:
            content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image}},
            ]
    else:
        if as_file:
            raise ValueError(
                "local files must be rendered to images first; "
                "file_url is only used for public URLs"
            )
        mime, _ = mimetypes.guess_type(image)
        if not mime or not mime.startswith("image/"):
            mime = "image/png"
        with open(image, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
    return {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
    }

def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", required=True)
    ap.add_argument("--api-key", default=os.environ.get("VISION_API_KEY") or cfg.get("api_key"))
    ap.add_argument("--base-url", default=os.environ.get("VISION_API_ENDPOINT") or cfg.get("endpoint") or DEFAULT_ENDPOINT)
    ap.add_argument("--model", default=os.environ.get("VISION_API_MODEL") or cfg.get("model") or DEFAULT_MODEL)
    ap.add_argument("--compact", action="store_true", help="focused fact-only extraction (fewer tokens)")
    ap.add_argument("--prompt", help="specific question to ask about the image")
    ap.add_argument("--file", action="store_true", help="treat input as a file (PDF) via file_url; requires a public URL")
    ap.add_argument("--max-tokens", type=int, default=int(cfg.get("max_tokens") or DEFAULT_MAX_TOKENS))
    args = ap.parse_args()
    # Clamp to the model's real output cap (fallback models may be smaller).
    cap = MODEL_MAX_TOKENS.get(args.model)
    if cap:
        args.max_tokens = min(args.max_tokens, cap)

    if not args.api_key or "PASTE" in args.api_key.upper():
        print("ERROR: no free vision-API key configured. Put your Zhipu key in config.json (see config.json.example).", file=sys.stderr)
        sys.exit(3)
    if args.file and not is_url(args.image):
        print(
            "ERROR: --file requires a public http(s) URL; local PDFs must be "
            "rendered to images first (use vision.py).",
            file=sys.stderr,
        )
        sys.exit(2)
    if args.file and args.model not in MODEL_SUPPORTS_FILES:
        print(
            f"ERROR: model {args.model} does not support file_url input; "
            f"use one of: {', '.join(sorted(MODEL_SUPPORTS_FILES))}.",
            file=sys.stderr,
        )
        sys.exit(2)
    if not is_url(args.image) and not os.path.isfile(args.image):
        print(f"ERROR: image not found: {args.image}", file=sys.stderr)
        sys.exit(2)

    prompt = args.prompt or (COMPACT_PROMPT if args.compact else FULL_PROMPT)
    if args.compact and args.prompt:
        prompt = args.prompt + "\nOnly return facts; do not expand into analysis."

    payload = json.dumps(
        build_payload(args.image, args.model, prompt, args.max_tokens, as_file=args.file)
    ).encode("utf-8")
    req = urllib.request.Request(
        args.base_url,
        data=payload,
        headers={
            "Authorization": f"Bearer {args.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout_ms = int(cfg.get("timeout_ms") or DEFAULT_TIMEOUT_MS)
    sys.stderr.write(f"[vision-api] model={args.model} endpoint={args.base_url} compact={args.compact}\n")
    try:
        with urllib.request.urlopen(req, timeout=timeout_ms / 1000.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            body = ""
        zcode = None
        try:
            zcode = json.loads(body).get("error", {}).get("code")
        except Exception:
            pass
        sys.stderr.write(f"[vision-api-error] status={exc.code} zhipu_code={zcode}\n")
        print(f"ERROR: API HTTP {exc.code}: {body or exc.reason}", file=sys.stderr)
        if exc.code == 429:
            print("Rate limited (free tier). The caller applies retry/fallback policy.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 - surface any network/API error to the agent
        print(f"ERROR: API call failed: {exc}", file=sys.stderr)
        print("Hint: check the provider docs for the current free model name; update config.json if needed.", file=sys.stderr)
        sys.exit(1)

    try:
        raw = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print("ERROR: unexpected API response shape:", file=sys.stderr)
        print(json.dumps(data, ensure_ascii=False)[:2000], file=sys.stderr)
        sys.exit(1)

    text = raw if isinstance(raw, str) else ""
    # Built-in prompts should produce a substantial reply. A too-short reply
    # (e.g. an empty stub under free-tier load) is a silent failure: HTTP 200
    # but useless output. Signal it so the caller jumps to the next free model.
    min_reply_chars = int(
        os.environ.get("VISION_MIN_REPLY_CHARS")
        or cfg.get("min_reply_chars")
        or DEFAULT_MIN_REPLY_CHARS
    )
    if not args.prompt and len(text.strip()) < min_reply_chars:
        sys.stderr.write(
            f"[vision-api-tooshort] model={args.model} reply={len(text.strip())} chars"
            f" < min_reply_chars={min_reply_chars}\n"
        )
        print(
            f"ERROR: vision reply too short ({len(text.strip())} chars); "
            "treating as failed.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("===== Vision model reply =====")
    print(text)
    print("===== end =====")


if __name__ == "__main__":
    main()
