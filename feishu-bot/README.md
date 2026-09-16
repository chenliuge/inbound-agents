# 飞书 CLI（Lark MCP 工具）

飞书官方提供的 [`lark-mcp`](https://github.com/larksuite/lark-openapi-mcp) CLI，可以让 Claude Code /
Cursor 等 AI 编程工具通过 MCP 协议直接调用飞书开放平台 API（发消息、查文档、建多维表格等），
用于本地调试 `feishu-bot`、或让 Agent 直接读写飞书数据。这是独立于 `app.py`（webhook 中间服务）
的开发工具，不需要部署，按需在本地运行即可。

## 前置条件

- Node.js（LTS 版本即可），安装后用 `node -v` / `npm -v` 确认
- 一个飞书自建应用的 **App ID** 和 **App Secret**（[飞书开放平台](https://open.feishu.cn/) 创建，
  或直接复用 `app.py` 里 `BOTS` 字典中某个 bot 的 `app_id` / `secret`）

## 安装 & 运行

无需全局安装，用 `npx` 直接运行最新版本：

```bash
npx -y @larksuiteoapi/lark-mcp mcp -a <your_app_id> -s <your_app_secret>
```

常用可选参数：

| 参数 | 说明 |
|---|---|
| `-d, --domain` | 飞书用 `https://open.feishu.cn`（默认）；国际版 Lark 用 `https://open.larksuite.com` |
| `-l, --language` | 工具描述语言，`zh` 或 `en`（默认 `en`） |
| `-t, --tools` | 启用的 API 工具集，逗号分隔（默认 `preset.default`） |
| `--oauth` | 开启用户级 OAuth 登录（需要 `user_access_token`） |

## 接入 Claude Code

在项目根目录的 `.mcp.json`（本地文件，已加入 `.gitignore`，不要提交真实密钥）中添加：

```json
{
  "mcpServers": {
    "lark-mcp": {
      "command": "npx",
      "args": [
        "-y", "@larksuiteoapi/lark-mcp", "mcp",
        "-a", "<your_app_id>",
        "-s", "<your_app_secret>",
        "-l", "zh"
      ]
    }
  }
}
```

模板见仓库根目录的 `.mcp.json.example`，复制为 `.mcp.json` 并填入密钥即可。

## 用户身份登录（可选）

需要以真实用户身份（而非应用身份）调用部分 API 时，先登录获取 `user_access_token`：

```bash
npx -y @larksuiteoapi/lark-mcp login -a <your_app_id> -s <your_app_secret>
npx -y @larksuiteoapi/lark-mcp whoami   # 查看已登录的会话
```

登录后在 `.mcp.json` 里加上 `"--oauth", "--token-mode", "user_access_token"` 即可使用用户级权限。

参考文档：[飞书 CLI 安装指南](https://open.feishu.cn/document/no_class/mcp-archive/feishu-cli-installation-guide)
