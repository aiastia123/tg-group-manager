# TG Group Manager Bot

Telegram 群组管理 Bot，基于 python-telegram-bot v21。

## 功能

| 模块 | 命令 | 说明 |
|------|------|------|
| **用户管理** | `/kick` `/ban` `/tempban` `/unban` `/mute` `/unmute` | 踢出/封禁/临时封禁/禁言 |
| **警告系统** | `/warn` `/warns` `/resetwarns` | 警告用户，N次自动踢 |
| **邀请管理** | `/invite` `/invites` `/revoke` `/whoinvited` | 创建/查看/撤销邀请链接，追踪邀请来源 |
| **管理员** | `/setadmin` `/removeadmin` `/admins` | 设置/取消/查看管理员 |
| **消息管理** | `/del` `/pin` `/unpin` `/unpinall` `/announce` | 删除/置顶/取消置顶/群公告 |
| **入群验证** | 自动 | 新用户数学验证码，超时自动踢 |
| **群规** | `/setrules` `/rules` | 设置/查看群规 |
| **配置** | `/settings` `/setconfig` | 查看/修改群组配置 |
| **用户信息** | `/info` `/note` `/tags` | 查看信息/备注/标签 |
| **黑名单** | `/blacklist` `/unblacklist` `/blacklists` | 黑名单管理 |
| **敏感词** | `/addword` `/delword` `/words` | 敏感词过滤 |
| **举报** | `/report` `/reports` `/resolve` | 举报系统 |
| **日志** | `/logs` | 操作日志 |

## 部署

### Docker（推荐）

```bash
# 1. 克隆仓库
git clone <repo-url> && cd tg-group-manager

# 2. 创建 .env 文件
cp .env.example .env
# 编辑 .env，填入 BOT_TOKEN

# 3. 启动
docker compose up -d
```

### 手动运行

```bash
pip install -r requirements.txt
export BOT_TOKEN=your_token
python bot.py
```

## 配置项

首次部署后，Bot 使用默认配置。在群内使用 `/setconfig <key> <value>` 动态修改：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `warn_limit` | 3 | 警告上限，达到自动踢 |
| `new_user_mute_minutes` | 5 | 新用户静默期（分钟），0=关闭 |
| `flood_messages` | 5 | 洪水检测消息数 |
| `flood_seconds` | 5 | 洪水检测时间窗（秒） |
| `link_filter` | false | 是否过滤链接 |
| `media_filter` | false | 是否过滤媒体 |
| `welcome_enabled` | true | 是否启用欢迎消息 |
| `goodbye_enabled` | false | 是否启用告别消息 |
| `captcha_enabled` | true | 是否启用入群验证 |
| `captcha_timeout` | 120 | 验证超时（秒） |
| `auto_delete_seconds` | 0 | 自动删除消息（秒），0=关闭 |
| `forward_filter` | false | 是否过滤转发消息 |

## 用法说明

大多数管理命令需要**回复目标用户的消息**或提供**用户 ID**。

```text
/kick          → 回复消息踢出
/ban @reason   → 回复消息封禁
/warn 太水了    → 回复消息警告，原因"太水了"
/mute 30       → 回复消息禁言30分钟
/invite 60 5   → 创建邀请链接，60分钟有效，限5人使用
/info          → 回复消息查看用户信息
/report 发广告  → 回复消息举报
```

## 权限模型

- **TG 群主/管理员**：自动识别，拥有所有权限
- **Bot 管理员**：通过 `/setadmin` 由 TG 管理员任命，可使用所有管理命令
- **普通用户**：仅可使用 `/rules` `/report`

## 存储

SQLite，数据文件 `data/bot.db`，Docker 部署时通过 volume 持久化。
