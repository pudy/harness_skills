# opencode/codebuddy-auth

opencode 用 CodeBuddy 订阅模型的部署说明（不维护源码，直接用 npm 官方原版插件 `@shatyuka/opencode-codebuddy-auth`）。

> 对应 pi 侧的同名扩展见 `pi/codebuddy-auth`。本目录只是 opencode 的**部署配置模板**，不含插件源码——从 npm 装原版，靠配置文件定制。

## 三步部署

1. **合并配置**：把下面 `opencode.jsonc` 模板里的 `plugin` 与 `model` 合并进 `~/.config/opencode/opencode.jsonc`（保留你已有的 provider 等配置）。

2. **装插件**（全局）：
   ```bash
   opencode plugin @shatyuka/opencode-codebuddy-auth -g
   ```

3. **登录 + 选模型**：
   - 打开 opencode，用 `/connect codebuddy` 走浏览器 IOA 登录；
   - `/model` 里选 `codebuddy/deepseek-v4-flash`（默认已配好，最省额度 x0.05）。

## 说明 / 注意

- **不维护源码**：升级用 `opencode plugin @shatyuka/opencode-codebuddy-auth -g --force` 拉最新 npm 版即可。
- **凭据分离**：插件 token 存 `~/.config/opencode/codebuddy.json`（权限 0600），与官方 CodeBuddy 客户端登录态互不影响。
- **版本小坑**：`opencode providers login codebuddy` 这个 CLI 命令不加载插件、会报 `fetch() URL is invalid`，属正常——请用会话内 `/connect codebuddy` 登录。
- **`opencode run -i` 非长驻**：`run` 处理完一条消息即退出；要长驻监督会话用 `opencode`（TUI）或 tmux。
- 模板中 `model` 默认 `codebuddy/deepseek-v4-flash`（CodeBuddy 侧计费权重最低）。
