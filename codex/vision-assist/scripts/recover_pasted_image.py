#!/usr/bin/env python3
"""Recover the most recent image the user pasted into a Codex conversation.

Searches the newest Codex session files for pasted images in two formats:
  1. Desktop app: event_msg entries of type user_message carrying non-empty
     `images` / `local_images` arrays (attachments are recorded even when the
     active model cannot render them).
  2. CLI:         response_item lines containing
     "image_url":"data:image/...;base64,..." content parts.

On success it prints the image path (the original local file when it still
exists, otherwise a temporary file reconstructed from base64) and exits 0.
When nothing is found it prints a short explanation and exits 1.

The search is deliberately strict: it only matches the two formats above and
never bare "data:image" text, so reasoning/tool-call mentions cannot false
positive.

Usage:
  python recover_pasted_image.py [--session <file>] [--max-files 20]
"""

import argparse
import base64
import json
import os
import platform
import re
import sys
import tempfile

SESSIONS_ROOT = os.path.expanduser("~/.codex/sessions")

# CLI format: JSON content part with an image_url data URL.
DATA_URL_RE = re.compile(r'"image_url"\s*:\s*"(data:image/[^"]+)"')
# Nearby hints for the original local file.
FILE_URL_RE = re.compile(r'file:///([^")\s]+\.(?:png|jpe?g|webp|bmp|gif))', re.I)
QUOTED_PATH_RE = re.compile(r'([A-Za-z]:\\[^"]*\.(?:png|jpe?g|webp|bmp|gif))', re.I)

MIME_EXT = {
    "png": ".png",
    "jpeg": ".jpg",
    "jpg": ".jpg",
    "webp": ".webp",
    "bmp": ".bmp",
    "gif": ".gif",
}


def collect_session_files(max_files):
    files = []
    if not os.path.isdir(SESSIONS_ROOT):
        return files
    for root, _dirs, names in os.walk(SESSIONS_ROOT):
        for name in names:
            if not name.endswith(".jsonl"):
                continue
            p = os.path.join(root, name)
            try:
                files.append((p, os.path.getmtime(p)))
            except OSError:
                continue
    files.sort(key=lambda t: t[1], reverse=True)
    return [p for p, _ in files[:max_files]]


def decode_data_url(data_url):
    """Return (mime_ext, raw_bytes) from a data:image/...;base64,... URL."""
    head, _, b64 = data_url.partition(",")
    mime = head.split(":")[1].split(";")[0] if ":" in head else ""
    ext = MIME_EXT.get(mime.split("/")[-1].lower(), ".png")
    return ext, base64.b64decode(b64)


def write_temp_image(raw, ext):
    fd, path = tempfile.mkstemp(prefix="codex-vision-", suffix=ext)
    with os.fdopen(fd, "wb") as fh:
        fh.write(raw)
    return path


def desktop_candidates(payload):
    """Candidate image references from a desktop user_message payload."""
    out = []
    for key in ("local_images", "images"):
        raw = payload.get(key) or []
        if isinstance(raw, str):
            raw = [raw]
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                for k in ("path", "file", "url"):
                    v = item.get(k)
                    if isinstance(v, str) and v.strip():
                        out.append(v.strip())
    return out


def resolve_candidate(candidate):
    """Turn a candidate string into a usable image path or None."""
    if candidate.startswith("data:image/"):
        try:
            ext, raw = decode_data_url(candidate)
            return write_temp_image(raw, ext), "reconstructed from base64"
        except Exception as exc:  # malformed data URL
            sys.stderr.write(f"note: skipping malformed data URL: {exc}\n")
            return None
    if candidate.startswith("file:///"):
        p = candidate[len("file:///"):]
        p = os.path.normpath(p.replace("/", os.sep))
    else:
        p = candidate
    if os.path.isfile(p):
        return p, "original file"
    return None


def scan_session_file(path):
    """Scan one session file from newest line to oldest; return (path, source_note) or None."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError as exc:
        sys.stderr.write(f"note: cannot read session file {path}: {exc}\n")
        return None

    # Walk from the end: the newest activity is at the bottom.
    for line in reversed(lines):
        # Desktop format fast path.
        if '"type":"user_message"' in line and '"local_images"' in line:
            try:
                j = json.loads(line)
                payload = j.get("payload", {})
                if payload.get("type") != "user_message":
                    continue
                for cand in desktop_candidates(payload):
                    resolved = resolve_candidate(cand)
                    if resolved:
                        return resolved[0], f"{path} ({resolved[1]})"
            except (ValueError, TypeError):
                continue

        # CLI format fast path.
        if '"image_url"' in line and "data:image/" in line:
            m = DATA_URL_RE.search(line)
            if not m:
                continue
            # Prefer an original path mentioned on the same line.
            fm = FILE_URL_RE.search(line)
            pm = QUOTED_PATH_RE.search(line)
            for p in (fm.group(1) if fm else None, pm.group(1) if pm else None):
                if p and os.path.isfile(p):
                    return p, f"{path} (original file)"
            try:
                ext, raw = decode_data_url(m.group(1))
                return write_temp_image(raw, ext), f"{path} (reconstructed from base64)"
            except Exception as exc:
                sys.stderr.write(f"note: skipping unreadable image in {path}: {exc}\n")
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session", help="restrict the search to one session JSONL file")
    ap.add_argument("--max-files", type=int, default=20,
                    help="how many newest session files to scan (default 20)")
    args = ap.parse_args()

    if platform.system().lower() == "windows":
        sys.stderr.write(
            "SKIP: session recovery is not applicable on Windows - the desktop "
            "app blocks image uploads for text-only models, so no pasted image "
            "is ever stored. Ask the user for the file path instead.\n"
        )
        sys.exit(1)

    if args.session:
        files = [args.session]
    else:
        files = collect_session_files(args.max_files)
    if not files:
        sys.stderr.write(f"ERROR: no session files under {SESSIONS_ROOT}\n")
        sys.exit(1)

    for f in files:
        found = scan_session_file(f)
        if found:
            print(found[0])
            sys.stderr.write(f"recovered from: {found[1]}\n")
            sys.exit(0)

    sys.stderr.write(
        "ERROR: no pasted image found in the most recent session files.\n"
        "Note for the agent: do NOT retry this command again in this thread; "
        "ask the user for the image path instead.\n"
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
