"""帮助命令"""
from telegram import Update
from telegram.ext import ContextTypes


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示帮助信息：/help"""
    # 私聊时发送完整帮助，群聊时提示私聊查看
    if update.effective_chat and update.effective_chat.type == "private":
        await update.effective_message.reply_text(_FULL_HELP)
    else:
        await update.effective_message.reply_text(
            "📖 完整命令列表已通过私聊发送给你！\n"
            "请查看与 bot 的私聊对话。"
        )
        try:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=_FULL_HELP,
            )
        except Exception:
            await update.effective_message.reply_text(
                "⚠️ 无法私聊发送帮助信息，请先私聊 bot 发送 /start 启动对话后再试。"
            )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """启动命令：/start"""
    if update.effective_chat and update.effective_chat.type == "private":
        await update.effective_message.reply_text(
            "👋 你好！我是群组管理 Bot。\n\n"
            "请将我添加到群组并赋予管理员权限，即可使用全部管理功能。\n\n"
            "发送 /help 查看所有可用命令。"
        )


_FULL_HELP = """📖 **群组管理 Bot 命令帮助**

━━━ 👤 用户管理 ━━━
/kick <用户ID或回复> [原因] — 踢出用户
/ban <用户ID或回复> [原因] — 永久封禁
/tempban <用户ID或回复> <分钟> [原因] — 临时封禁
/unban <用户ID或回复> — 解封用户
/mute <用户ID或回复> [分钟] — 禁言（默认60分钟）
/unmute <用户ID或回复> — 解除禁言

━━━ ⚠️ 警告系统 ━━━
/warn <用户ID或回复> [原因] — 警告用户
/warns <用户ID或回复> — 查看警告记录
/resetwarns <用户ID或回复> — 清除警告

━━━ 🔗 邀请链接 ━━━
/invite [过期分钟] [使用次数] — 创建邀请链接（私聊发送）
/invites — 查看邀请链接列表
/revoke <链接> — 撤销邀请链接
/whoinvited <用户ID或回复> — 查看邀请来源

━━━ 🛡️ 管理员 ━━━
/setadmin <用户ID> — 设为管理员
/removeadmin <用户ID> — 移除管理员
/admins — 查看管理员列表
/addperm <用户ID> <权限> — 添加权限
/delperm <用户ID> <权限> — 移除权限
/perms <用户ID> — 查看权限

━━━ 📝 消息管理 ━━━
/del — 删除回复的消息
/pin — 置顶回复的消息
/unpin — 取消置顶
/unpinall — 取消所有置顶
/announce <内容> — 发布群公告

━━━ ⚙️ 配置与信息 ━━━
/settings — 查看群组设置
/setconfig <配置项> <值> — 修改配置
/setrules <规则> — 设置群规
/rules — 查看群规
/info <用户ID或回复> — 查看用户信息
/note <用户ID或回复> <备注> — 设置用户备注
/tags <用户ID或回复> <标签> — 设置用户标签

━━━ 🚫 黑名单 ━━━
/blacklist <用户ID或回复> [原因] — 加入黑名单
/unblacklist <用户ID或回复> — 移出黑名单
/blacklists — 查看黑名单

━━━ 🔤 敏感词 ━━━
/addword <词语> — 添加敏感词
/delword <词语> — 删除敏感词
/words — 查看敏感词列表

━━━ 📢 举报 ━━━
/report <用户ID或回复> [原因] — 举报用户
/reports — 查看举报列表
/resolve <举报ID> — 处理举报

━━━ 📋 其他 ━━━
/logs — 查看操作日志
/help — 显示本帮助信息

💡 提示：大多数命令需要回复目标用户的消息，或提供用户 ID。
"""