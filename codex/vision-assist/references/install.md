# Installing OCR engines (per platform)

Run these in a normal terminal yourself, or explicitly authorize Codex to run them.

## Free vision API (Zhipu GLM, optional but free)

The API fallback in this skill only uses free models. To enable it:

1. Register at <https://open.bigmodel.cn> (Zhipu AI, bigmodel platform).
2. Create an API key in the console (free tier).
3. Copy `config.json.example` to `config.json` next to the skill and paste the
   key into `api_key`. Never paste the key into a chat message.

Free models (all free tier):

- `glm-4.6v-flash` (default; 128K context, 32K max output, image/video/file
  input, thinking mode toggle)
- `glm-4v-flash` (lightweight, fast, 16K context, 1K max output)
- `glm-4.1v-thinking-flash` (deep-reasoning vision, 64K context, 16K max output)

If no key is configured, OCR still works; the API fallback simply reports that
it is skipped.

## PaddleOCR (best Chinese; cross-platform)

- `pip install paddlepaddle paddleocr`
- x86_64 Windows/Linux: official wheels available.
- ARM Linux (many NAS) and macOS Apple Silicon: official wheels may be missing;
  check the PaddlePaddle install docs or use Tesseract instead.
- First run downloads models (needs network).

## Tesseract (lightweight fallback; Linux/macOS)

- Debian/Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-chi-sim`
- macOS: `brew install tesseract tesseract-lang`
- Windows: not needed (built-in OCR exists); optional builds available.
- Python wrapper: `pip install pytesseract Pillow`

## Windows built-in OCR

- No install required; always available on Windows.

## NAS / Linux 部署清单（Codex CLI）

代码本身已跨平台（纯 Python），NAS 上只需准备环境：

1. **Python 3**：确认 `python3 --version` 可用；没有就装
   `sudo apt install python3`（Debian/Ubuntu 系）或对应发行版包。
2. **Tesseract + 中文包**（推荐，ARM NAS 的稳妥选择）：
   `sudo apt install tesseract-ocr tesseract-ocr-chi-sim`
3. **可选：PaddleOCR**（仅 x86_64 NAS，中文效果更好）：
   `pip3 install paddlepaddle paddleocr`
   ARM（aarch64）NAS 官方轮子可能缺失，装不上就直接用 Tesseract，
   `vision.py` 会自动降级。
4. **配置文件**：把 Windows 上的 `config.json`（含智谱 key）原样拷到
   `~/.codex/skills/vision-assist/config.json`，跨平台通用。
5. **验证**：
   `python3 scripts/vision.py --check`
   期望输出 `platform: linux`，且 `tesseract: yes` 或 `paddleocr: yes`。

常见坑：

- `pip3` 不存在 → `sudo apt install python3-pip`
- 中文乱码/识别不出 → 缺 `tesseract-ocr-chi-sim` 语言包
- 会话找回：Linux（CLI）下可用，每线程只尝试一次；找不到就改为要路径
- 如果当前模型有原生视觉，provider 守卫会自动禁用技能，属正常行为

## Verify

```bash
python scripts/vision.py --check
```
