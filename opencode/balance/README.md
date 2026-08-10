# opencode/balance（TUI 插件）

在 opencode TUI 输入框右侧（`home_prompt_right` / `session_prompt_right` 插槽）显示当前模型的 API 账户余额。

- **OpenRouter** → `GET /api/v1/auth/key`（`limit_remaining`，即当前 key 的真实剩余额度）
- **其他 OpenAI 兼容 provider（如自建/公司 DeepSeek，New API 模式）** → `GET {baseURL}/dashboard/billing/subscription`（`soft_limit_usd`）+ `GET {baseURL}/dashboard/billing/usage`（`total_usage`，单位分）

## 特点

- **跟随会话内实际使用的模型**：余额随当前会话最后一条 assistant 消息用到的 `providerID/modelID` 显示
- **消息事件即时刷新**：`message.updated` 携带模型信息时立即刷新余额；切完模型发一句话即更新
- **防抖合并**：`session.updated` 等高频事件 2s 防抖合并，事件风暴下不空转
- **自适应心跳**：5 分钟无事件时补查一次余额（兜底），之后停止，不常驻轮询
- **请求超时**：所有余额查询 10s 超时（AbortController），API 挂起不会卡住插件
- **结果缓存**：同模型 5 分钟 TTL 缓存，模型没变不打网络请求
- **并发防护**：慢的旧请求晚返回不会覆盖新模型的余额（竞态守卫）
- 不存储密钥：key 从 `~/.local/share/opencode/auth.json` 按 provider 读取

> 注意：仅切换模型、不发送消息时是 opencode 的纯 TUI 本地状态，插件拿不到，因此**切完模型发一句话才刷新**（纯平台限制）。

## 安装

opencode 的 TUI 插件写在各 config 的 `plugin` 数组里，用**绝对路径**指向 JS 文件（TUI 不会扫描目录，`~` 也不会展开）。

1. 把 `balance.js` 放到你的插件目录，例如：
   ```bash
   mkdir -p ~/.config/opencode/tui-plugins
   cp balance.js ~/.config/opencode/tui-plugins/balance.js
   ```

2. 在 `~/.config/opencode/tui.json` 的 `plugin` 数组登记绝对路径：
   ```jsonc
   {
     "$schema": "https://opencode.ai/tui.json",
     "plugin": ["/home/YOUR_USER/.config/opencode/tui-plugins/balance.js"]
   }
   ```

3. 外部依赖：`balance.js` 用到了 `solid-js` 和 `@opentui/solid`。要保证它们在配置目录的 `node_modules` 里可被插件解析（本地插件不自动装依赖），在 `~/.config/opencode/` 里建 `package.json`：
   ```jsonc
   {
     "dependencies": {
       "solid-js": "*",
       "@opentui/solid": "*"
     }
   }
   ```
   然后在此目录执行 `bun install`（或 npm install）。

4. 重启 opencode 生效。
