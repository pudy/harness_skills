# harness_skills

个人技能/工具集仓库，按工具平台分类存放：

- `codex/` — Codex（桌面应用 / CLI）技能

## codex/vision-assist

识图技能：为不带原生视觉的文本模型提供读图能力（截图、照片、UI、图表、PDF）。

- 免费视觉 API 优先（智谱 GLM：`glm-4.1v-thinking-flash` → `glm-4.6v-flash` → `glm-4v-flash`），每个模型只试一次，失败自动切下一个
- 支持 PDF（本地优先）：先原生抽取文本层（pdfplumber，准确、快），检测到乱码（浏览器打印常见）或扫描件时自动转"渲染页面 + 视觉识别"，最后本地 OCR 兜底
- 支持公网 PDF URL 与图片 URL（先下载到本地再走同一套流程）
- 全部失败后降级本地 OCR（Windows 内置 / PaddleOCR / Tesseract）
- 从不使用付费 API；付费识图由独立技能负责
- 跨平台：Windows / Linux / macOS
- 安装与用法见 `codex/vision-assist/SKILL.md`
