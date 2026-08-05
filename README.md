# harness_skills

个人技能/工具集仓库，按工具平台分类存放：

- `codex/` — Codex（桌面应用 / CLI）技能

## codex/vision-assist

识图技能：为不带原生视觉的文本模型提供读图能力（截图、照片、UI、图表、PDF）。

- 免费视觉 API 优先（智谱 GLM：`glm-4.6v-flash` → `glm-4.1v-thinking-flash` → `glm-4v-flash`），每个模型只试一次，失败自动切下一个
- 支持本地 PDF（渲染成页面图）与公网 PDF URL（原生 file_url 直读），也支持图片 URL
- 全部失败后降级本地 OCR（Windows 内置 / PaddleOCR / Tesseract）
- 从不使用付费 API；付费识图由独立技能负责
- 跨平台：Windows / Linux / macOS
- 安装与用法见 `codex/vision-assist/SKILL.md`
