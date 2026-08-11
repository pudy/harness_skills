# pi/codebuddy-auth（pi 扩展 extension）

用 CodeBuddy 账号登录 pi，直接在 pi 里调用 CodeBuddy 订阅内的模型（DeepSeek、GLM、Kimi、MiniMax 等）。模型列表**实时来自你账号的 `/v3/config`**，账户里有什么就显示什么，没有内置静态模型目录。

单文件扩展（`index.ts`），基于 [Lbryany/pi-plugins](https://github.com/Lbryany/pi-plugins) 的 `extensions/codebuddy` 改造：

- **账户驱动模型列表**：模型 100% 来自 `GET /v3/config`（企业账号再叠加 `/console/enterprises/{id}/config/models`）。账户新增的 DeepSeek 等模型会自动出现。
- **去掉 cli/chat 可见性过滤**：原版会按 `cli` agent / `chat` 标签裁剪模型，本版全量展示。
- **默认国内站**：`https://copilot.tencent.com` + `platform=CLI`（与 opencode 的 codebuddy 插件一致），可用 `PI_CODEBUDDY_PLATFORM` 覆盖。
- 保留原版其余逻辑：浏览器 OAuth 登录、token 刷新、CodeBuddy 网关请求 envelope（`agent:"cli"`、CLI 请求头）、个人/企业账号支持。

## 安装

pi 的扩展放在全局 `~/.pi/agent/extensions/`，改完用 `/reload` 或重启生效。

```bash
mkdir -p ~/.pi/agent/extensions/codebuddy-account-driven
cp index.ts ~/.pi/agent/extensions/codebuddy-account-driven/index.ts
```

## 使用

1. pi 里执行 `/reload`（或重启）
2. `/login codebuddy` → 浏览器授权登录（国内站，platform=CLI）
3. `/model` → 展开 `codebuddy` 组，选择模型（如 `codebuddy/deepseek-v4-pro`、`codebuddy/deepseek-v4-flash`）
4. 想钉在顶部：把模型加进 `~/.pi/agent/settings.json` 的 `enabledModels`

## 可覆盖的环境变量

| 环境变量 | 默认 | 作用 |
|---|---|---|
| `PI_CODEBUDDY_PLATFORM` | `CLI` | 认证 platform（国内站 `CLI` / 国际站 `codebuddy`） |
| `PI_CODEBUDDY_ENVELOPE` | 开 | 请求 envelope 总开关；`off` 时纯 OpenAI body |
| `PI_CODEBUDDY_AGENT_TAG` | `cli` | 逐条 user message 附加的 `agent` 标记 |
| `PI_CODEBUDDY_REASONING_EFFORT` | `high` | 默认 reasoning_effort |
| `PI_CODEBUDDY_STREAM_OPTIONS` | 开 | 注入 `stream_options.include_usage` |
| `PI_CODEBUDDY_TEMPERATURE` | `1` | 默认 temperature |
| `PI_CODEBUDDY_CLI_HEADERS` | 开 | 额外 CLI 请求头 |
| `PI_CODEBUDDY_DEBUG_LOG` | 无 | 本地 JSONL 调试日志路径 |
| `PI_CODEBUDDY_PROBE_CLOUD_CONFIG` | 关 | 记录 /v3/config 详细响应摘要到调试日志 |

## 与原版的差异

| | Lbryany 原版 | 本版 |
|---|---|---|
| 模型来源 | 内置静态目录(2026-07-23) + /v3/config overlay | **纯 /v3/config** |
| 静态兜底 | 有（网络失败回退静态快照） | 无（失败保留上次成功缓存） |
| 可见性过滤 | cli agent / chat 标签裁剪 | 无，全量展示 |
| 默认站点 | www.codebuddy.ai (国际) | copilot.tencent.com (国内) |
| 默认 platform | codebuddy | CLI |

## 验证

- `npm install && npm run typecheck`（tsc 通过）
- 已用真实 pi 0.84.1 + 真实账号验证：`/v3/config` 拉取 25 个模型（含 `deepseek-v4-pro`、`deepseek-v4-flash`、`custom:deepseek-v4-*`），pi 集成 `getAvailableSnapshot` 正常显示。

> 配合 [pi/balance](../balance/README.md) 使用：balance 扩展会读 `/v3/config` 显示 CodeBuddy 模型积分单价，两个扩展互不冲突。
