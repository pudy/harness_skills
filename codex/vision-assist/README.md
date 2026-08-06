# codex/vision-assist（技能 skill）

识图技能：为不带原生视觉的文本模型提供读图能力（截图、照片、UI、图表、PDF）。

## 原理 & 能力

- **免费视觉 API 优先**（智谱 GLM 免费模型链：`glm-4.1v-thinking-flash` → `glm-4.6v-flash` → `glm-4v-flash`），每个模型只试一次，失败/限流自动切下一个
- **PDF 本地优先**：先原生抽取文本层（pdfplumber，准确、快）；检测到乱码（浏览器打印常见）或扫描件时，自动转「渲染页面 + 视觉识别」；最后本地 OCR 兜底
- **支持公网 URL**：公网 PDF 与图片 URL 先下载到本地，再走同一套流程
- **全部失败后降级本地 OCR**（Windows 内置 / PaddleOCR / Tesseract），离线也能用
- **从不使用付费 API**；付费识图由独立技能负责，本技能保持解耦

## 界限（重要）

- `--mode ocr` 强制只走本地 OCR（隐私敏感图、无网、或需要带坐标的精确文本）
- 若当前模型**原生支持看图**（view_image 可用），则改用原生能力，不走本技能
- 本技能只对纯文本模型运行，`scripts/vision.py` 会读 `~/.codex/config.toml` 做 provider guard，非 `allowed_models` 时直接报错禁用

## 工作流

1. **粘贴的图**：Windows 上报无法自动恢复，让用户给文件路径；Linux/macOS 用 `recover_pasted_image.py --latest`（每线程一次）
2. **本地文件**：统一入口 `python scripts/vision.py --image "<路径>"`
3. **URL**：先下载到本地再走同一套流程

## 配置

复制 `config.json.example` 为 `config.json` 并填你的智谱 API key（仅用免费模型）：

- `model` + `fallback_models`：免费模型链
- `allowed_models`：允许使用本技能的纯文本模型
- `pdf_max_pages` / `pdf_dpi`：PDF 渲染参数

## 跨平台

Windows / Linux / macOS。详细安装与用法见 `SKILL.md`。
