# Vision API setup (optional)

Use a FREE external multimodal model as a "vision preprocessor" when local OCR
is insufficient and the user agrees to send the image to a third-party service.
This skill never uses paid providers.

## Local OCR upgrade: PaddleOCR (recommended for Chinese)

Windows built-in OCR is decent but weak on dense Chinese UI text. PaddleOCR is
free, local, and noticeably more accurate for Chinese.

- Install (one-time, needs network): `pip install paddleocr paddlepaddle`
- Run: `python scripts/ocr_paddle.py --image "<path>" [--lang ch]`
- Output includes text boxes and confidence. Combine with Windows OCR results
  when in doubt.
- If install is not possible, keep using `scripts/ocr.ps1`.

## Requirements

- A free Zhipu API key (registration at open.bigmodel.cn required; free tier).
- Network access; in sandboxed Codex sessions the API call may need approval.
- Image leaves the local machine. Confirm with the user for sensitive images.

## Zhipu (default free provider)

- Endpoint: `https://open.bigmodel.cn/api/paas/v4/chat/completions`
- Free models (tried in this order): `glm-4.1v-thinking-flash` (default since
  2026-08-05, while `glm-4.6v-flash` is persistently overloaded), `glm-4.6v-flash`
  (fastest when healthy; restore as primary once a direct call succeeds),
  `glm-4v-flash` (oldest but stable; 1024-token output cap)
- Only `glm-4.6v-flash` and `glm-4.1v-thinking-flash` accept `file_url` input
  (PDF/documents); `glm-4v-flash` is image-only.
- Docs: <https://docs.bigmodel.cn/cn/guide/start/model-overview>

## PDF and URL input

- **Local-first, always**: a PDF is first read from its native text layer with
  pdfplumber - accurate, fast, free. Only when extraction returns nothing
  (scanned or image-only PDFs) or looks garbled do pages get rendered
  (PyMuPDF, `pip install PyMuPDF`) and read through the vision API → OCR
  pipeline. See `pdf_max_pages` / `pdf_dpi` in config.
- **Garbled-text detection**: browser-printed PDFs (Chrome/Skia) sometimes
  have a broken ToUnicode mapping - extraction returns non-empty garbage
  (private-use-area / Kangxi characters, or excessive `?`). The pipeline
  treats extraction as garbled when suspicious characters exceed ~10% (PUA /
  Kangxi / replacement / control) or `?` exceeds 30%, and falls back to
  rendered pages automatically.
- **Public PDF URL** (`--url https://.../x.pdf`): downloaded first, then the
  same local-first flow applies.
- **Public image URL** (`--url https://.../x.png`): downloaded to a temp file
  first, so local OCR fallback still applies.
- Low-level: `describe_with_image.py --file <pdf-url>` still supports Zhipu's
  native `file_url` reading (glm-4.6v-flash / glm-4.1v-thinking-flash only),
  but the default pipeline no longer relies on it. Zhipu's `file_url` only
  accepts http(s) URLs (base64 data URLs are rejected, error 1214).

## Other free providers

- Any OpenAI-compatible free endpoint can be used by editing `config.json`
  (e.g. Qwen-VL free tier, Google AI Studio free tier). Paid providers are out
  of scope for this skill by design.

## Config (`config.json` next to the skill)

```json
{
  "api_key": "your-free-zhipu-key",
  "endpoint": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
  "model": "glm-4.1v-thinking-flash",
  "fallback_models": ["glm-4.6v-flash", "glm-4v-flash"],
  "allowed_models": ["deepseek-v4-flash", "deepseek-v4-pro"],
  "timeout_ms": 60000,
  "max_tokens": 4000,
  "min_reply_chars": 10,
  "pdf_max_pages": 20,
  "pdf_dpi": 150
}
```

Env overrides (first match wins): `VISION_API_KEY`, `VISION_API_MODEL`,
`VISION_API_ENDPOINT`, `VISION_TIMEOUT_MS`, `VISION_ALLOWED_MODELS`,
`VISION_MIN_REPLY_CHARS`.

The free API chain is: `glm-4.1v-thinking-flash` → `glm-4.6v-flash` →
`glm-4v-flash` → local OCR. `fallback_models` is tried in order when the
primary model is rate-limited (429) or fails, before the pipeline falls back
to local OCR.

Retry policy (each free model is tried ONCE, then the next model, then OCR):

- No same-model retries: any failure moves straight to the next free model.
  Rate limits are per model, so switching models fixes overload faster than
  waiting on the same one.
- Permanent request errors (HTTP 400/404, bad model name) and too-short
  replies jump straight to the next free model.
- Permanent account-level errors (HTTP 401/403) stop the API chain immediately
  and fall back to local OCR (retrying is pointless - same key, same problem).
- A successful call whose reply is shorter than `min_reply_chars` (built-in
  prompts only; custom `--prompt` answers are never length-checked) is treated
  as a failure and jumps straight to the next free model.

With 3 free models, the worst case is 3 failed calls (no waits) before local
OCR, so the API chain fails fast instead of burning backoff time.

Free-tier rate limits are per model and mostly concurrency-based (Zhipu docs:
"不同模型设有独立的并发限制"); switching models helps for model-level
overload (1305) but not for account-level auth/quota problems.

## Recommended pattern

1. Default (`vision.py --image <path>`): the free vision API reads the whole
   image first (text + layout + states). This is the best quality path.
2. If the API is rate-limited or unreachable, `vision.py` automatically falls
   back to local OCR, so a read still succeeds.
3. `--mode ocr` forces local OCR (privacy-sensitive images, offline use, or
   exact text with coordinates). `--mode api` forces the API only.
4. Merge when needed: OCR text is authoritative for exact labels; the vision
   reply fills in structure, icons, and spatial context.

For token economy, use `--compact` (or a focused `--prompt`) so the vision
model returns only the facts you asked for instead of a full description.

For web pages/UI, prefer reading the page DOM/accessibility tree over both.
