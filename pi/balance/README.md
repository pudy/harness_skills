# pi/balance（pi 扩展 extension）

在 pi 底部状态栏显示当前 provider 的 API 账户余额，并提供 `/balance` 命令手动查看明细。

- **OpenRouter** → `GET /api/v1/auth/key`（`limit_remaining`，即当前 key 的真实剩余额度）
- **DeepSeek** → `GET https://api.deepseek.com/user/balance`（`total_balance`）
- **其他 provider（如 codebuddy）** → 无公开余额接口，状态栏显示 `unsupported`，不会残留旧余额

## 特点

- **自动跟随 provider**：余额随当前会话模型所属的 provider 显示，切到别的 provider 会自动更新
- 刷新时机：会话启动 + 切换 provider + 每轮任务结束后；同 provider 内切模型不打请求；60 秒内自动请求合并防抖
- 不存储密钥：key 走 pi 凭证链（`~/.pi/agent/auth.json` 或环境变量）自动解析
- 无定时器、无轮询

## 安装

pi 的扩展放在全局 `~/.pi/agent/extensions/` 或项目 `.pi/extensions/`，改完用 `/reload` 或重启生效。

1. 把 `balance.ts` 放入扩展目录：
   ```bash
   mkdir -p ~/.pi/agent/extensions
   cp balance.ts ~/.pi/agent/extensions/balance.ts
   ```

2. `pi` 里执行 `/reload`，或重启 pi。

3. 使用：
   - `/balance` — 查看当前 provider 余额
   - `/balance deepseek` / `/balance openrouter` — 指定某平台查询
