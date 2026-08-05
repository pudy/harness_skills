---
name: vision-assist
description: Read and interpret image files and PDFs (screenshots, photos, UI captures, charts, documents) when the active model lacks native vision input. Use when the user asks Codex to look at, read, analyze, or summarize an image, screenshot, photo, chart, UI capture, PDF, or document, or when image/view_image input fails with "does not support image inputs", or when a message contains "image content omitted". Uses a FREE vision API first (Zhipu GLM free models only) and automatically falls back to local OCR (Windows built-in / PaddleOCR / Tesseract) when the API is rate-limited or unreachable. PDFs are read via local native text extraction first, falling back to page rendering + vision/OCR for scanned files. Never uses paid APIs; paid image recognition is another skill's responsibility. Cross-platform.
---

# Vision Assist (图片读取与视觉辅助)

Turn image files into readable text when the active model is text-only. Cross-platform.

## Boundary (important)

- This skill uses the **free vision API first** (Zhipu GLM free models, chain:
  `glm-4.1v-thinking-flash` → `glm-4.6v-flash` → `glm-4v-flash`) and
  **automatically falls back to local OCR**
  (Windows built-in / PaddleOCR / Tesseract) when the API is rate-limited or
  unreachable.
- `--mode ocr` forces local OCR only (privacy-sensitive images, offline use, or
  exact text with coordinates). Most routine reads should just use the default.
- It **never calls paid APIs**. Paid image recognition is the future
  model-router skill's job and must stay decoupled from this skill.
- If the active model natively supports images (view_image works), use that
  instead of this skill.

## Provider guard

This skill only runs for text-only models. `scripts/vision.py` reads
`~/.codex/config.toml` and exits with an error when the current model is not in
`allowed_models` (configurable in `config.json`). If that happens, tell the user
the current model can already see images, so the skill is disabled by design.

## Workflow

1. **Pasted image?** On Windows, never attempt session recovery: the desktop
   app blocks image uploads for text-only models, so nothing is ever stored —
   ask the user for the file path. On Linux/macOS (e.g. Codex CLI on a NAS),
   run `recover_pasted_image.py --latest` **once per thread**. It looks in the
   newest Codex session files (desktop app format and CLI format). If it fails,
   do NOT retry it in this thread — ask the user for the file path instead.
2. **Local file?** Run the unified entry:
   `python scripts/vision.py --image "<path>"`
   By default it calls the free vision API first and, if that fails (rate limit,
   network), automatically falls back to local OCR.
3. **PDF?** Local-first: the PDF's text layer is extracted directly with
   pdfplumber (accurate, fast, zero API cost). If nothing comes out (scanned
   or image-based PDF) or the extraction looks garbled (broken ToUnicode
   mapping, e.g. Chrome print-to-PDF), pages are rendered (PyMuPDF) and read
   through the same API → OCR pipeline (`pdf_max_pages` / `pdf_dpi` in config).
4. **Public URL?** `python scripts/vision.py --url "<http(s) url>"` works for
   images and PDFs; everything is downloaded to a temp file first (PDFs then
   follow the local-first flow, images keep OCR fallback).
5. **Local-only / exact text?** Rare; force OCR with:
   `python scripts/vision.py --image "<path>" --mode ocr`
   If the result is garbled, retry with tuning flags:
   `python scripts/vision.py --image "<path>" --scale 2`
   `python scripts/vision.py --image "<path>" --region "x,y,width,height"`
   `python scripts/vision.py --image "<path>" --grayscale`
6. **Focused fact extraction** (error messages, key numbers): add `--compact`
   or a `--prompt "..."` to the API path.
7. **Missing engine (non-Windows only):** tell the user plainly, then show the
   matching install command from `references/install.md` and ask before
   installing anything. On Windows, the built-in OCR always exists, so never
   suggest PaddleOCR there.
8. For web pages or UI inside a browser, prefer reading the page
   DOM/accessibility text instead of OCR.

## Commands

If `python` is not on PATH (common in sandboxes), locate the bundled/usable
Python runtime first and call the scripts with its full path.

Engine + status check (one line, run once per thread when first needed):

```bash
python scripts/vision.py --check
```

Recover the most recent pasted image (once per thread at most; on Windows this
is skipped by design, so ask for a path instead):

```bash
python scripts/recover_pasted_image.py --latest
```

Unified read (free API first, automatic OCR fallback):

```bash
python scripts/vision.py --image "<path>"
python scripts/vision.py --latest
```

Force local OCR only (rare; privacy/offline/exact-text cases):

```bash
python scripts/vision.py --image "<path>" --mode ocr
```

## Config

Copy `config.json.example` to `config.json` next to the skill and fill in the
free Zhipu API key. `model` is the primary free vision model;
`fallback_models` in `config.json` are tried in order before local OCR.
`allowed_models` lists which text-only models activate the skill. Never put
paid-provider keys here.

## Rules

- Never modify the user's original image; only write temp outputs.
- Never send the user's image to a paid provider.
- Ask the user before sending a sensitive image to the free API.
- If the active model natively supports images, do not use this skill.
