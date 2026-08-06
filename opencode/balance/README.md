# opencode/balance（TUI 插件）

在 opencode TUI 输入框右侧（`home_prompt_right` / `session_prompt_right` 插槽）显示当前模型的 API 账户余额。

- **OpenRouter** → `GET /api/v1/auth/key`（`limit_remaining`，即当前 key 的真实剩余额度）
- **其他 OpenAI 兼容 provider（如自建/公司 DeepSeek，New API 模式）** → `GET {baseURL}/dashboard/billing/subscription`（`soft_limit_usd`）+ `GET {baseURL}/dashboard/billing/usage`（`total_usage`，单位分）

## 特点

- **跟随会话内实际使用的模型**：余额随当前会话最后一条 assistant 消息用到的 `providerID/modelID` 显示
- 刷新时机：启动 + `message.updated` / `session.updated` / `session.next.model.switched` 事件；按模型变化守卫，模型没变不打网络请求
- 不存储密钥：key 从 `~/.local/share/opencode/auth.json` 按 provider 读取
- 无定时器、无轮询

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
