# harness_skills

个人技能/工具集仓库，按工具平台分类存放。

| 目录 | 平台 | 类型 |
|------|------|------|
| `codex/` | Codex（桌面应用 / CLI） | 技能 (skill) |
| `pi/` | pi（coding agent） | 扩展 (extension) |

> 每个目录里放的是该平台可用的东西。**技能**（skill）走平台的技能机制（如 Codex 的 `SKILL.md`）；**扩展**（extension）走平台的扩展 API（如 pi 的 `~/.pi/agent/extensions/`）。

## codex/vision-assist（技能 skill）

识图技能：为不带原生视觉的文本模型提供读图能力（截图、照片、UI、图表、PDF）。

- 免费视觉 API 优先（智谱 GLM：`glm-4.1v-thinking-flash` → `glm-4.6v-flash` → `glm-4v-flash`），每个模型只试一次，失败自动切下一个
- 支持 PDF（本地优先）：先原生抽取文本层（pdfplumber，准确、快），检测到乱码（浏览器打印常见）或扫描件时自动转"渲染页面 + 视觉识别"，最后本地 OCR 兜底
- 支持公网 PDF URL 与图片 URL（先下载到本地再走同一套流程）
- 全部失败后降级本地 OCR（Windows 内置 / PaddleOCR / Tesseract）
- 从不使用付费 API；付费识图由独立技能负责
- 跨平台：Windows / Linux / macOS
- 安装与用法见 `codex/vision-assist/SKILL.md`

## pi/balance（扩展 extension）

余额查询扩展：自动在 pi 底部状态栏显示当前 provider 的账户余额，并提供 `/balance` 命令手动查看明细。

- **自动跟随 provider**：OpenRouter → `GET /api/v1/auth/key`（`limit_remaining`，即本 key 每月真实可花额度）；DeepSeek → `GET /api/v1/user/balance`
- 刷新时机：会话启动 / 切换 provider / 每轮任务结束后（60 秒内合并一次），避免无谓请求
- 不存储任何密钥，key 走 pi 的凭证链（`~/.pi/agent/auth.json` 或环境变量）自动解析
- 安装：把 `pi/balance/balance.ts` 放入 `~/.pi/agent/extensions/`，重启或 `/reload` 后生效
