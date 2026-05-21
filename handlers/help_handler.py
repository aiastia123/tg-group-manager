"""帮助命令"""
import time
from telegram import Update
from telegram.ext import ContextTypes
from services import database as db


async def _handle_view_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE, token: str):
    """处理 view_ 深链：发送待领取的私聊消息"""
    pending = db.get_pending_message(token)

    if not pending:
        await update.effective_message.reply_text("❌ 消息不存在或已被查看")
        return

    # 安全校验：确保是消息本人
    if pending["user_id"] != update.effective_user.id:
        await update.effective_message.reply_text("❌ 此消息不是发给你的")
        return

    # 标记为已领取
    db.claim_pending_message(token)

    # 发送消息内容
    await update.effective_message.reply_text(pending["content"])


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
    """启动命令：/start [深链参数]"""
    # 处理深链参数 — 验证码
    if context.args and context.args[0].startswith("verify_"):
        from handlers.captcha_welcome import handle_verify_deep_link
        token = context.args[0][7:]
        await handle_verify_deep_link(update, context, token)
        return

    # 处理深链参数 — 私聊查看敏感信息
    if context.args and context.args[0].startswith("view_"):
        token = context.args[0][5:]
        await _handle_view_deep_link(update, context, token)
        return

    # 处理深链参数 — 邀请链接
    if context.args and context.args[0].startswith("invite_"):
        token = context.args[0][7:]  # 去掉 "invite_" 前缀
        pending = db.get_pending_invite(token)

        if not pending:
            await update.effective_message.reply_text("❌ 邀请链接不存在或已被领取")
            return

        # 检查是否过期
        if pending["expires_at"] and pending["expires_at"] < time.time():
            await update.effective_message.reply_text("❌ 邀请链接已过期")
            return

        # 标记为已领取
        db.claim_pending_invite(token)

        # 构建邀请链接消息
        msg = f"🔗 你的邀请链接：\n\n{pending['link']}"
        if pending["member_limit"]:
            msg += f"\n使用次数限制：{pending['member_limit']}"

        # 尝试获取群名称
        try:
            chat = await context.bot.get_chat(pending["chat_id"])
            msg += f"\n群组：{chat.title}"
        except Exception:
            pass

        await update.effective_message.reply_text(msg)
        return

    # 普通启动
    if update.effective_chat and update.effective_chat.type == "private":
        await update.effective_message.reply_text(
            "👋 你好！我是群组管理 Bot。\n\n"
            "请将我添加到群组并赋予管理员权限，即可使用全部管理功能。\n\n"
            "发送 /help 查看所有可用命令。"
        )


_FULL_HELP = """📖 群组管理 Bot 命令帮助

━━━ 👤 用户管理 ━━━
/kick <用户ID或回复> [原因] — 踢出用户
/ban <用户ID或回复> [原因] — 永久封禁
/tempban <用户ID或回复> <分钟> [原因] — 临时封禁
/unban <用户ID或回复> — 解封用户
/mute <用户ID或回复> [分钟] — 禁言（默认60分钟）
/unmute <用户ID或回复> — 解除禁言

━━━ ⚠️ 警告系统 ━━━
/warn <用户ID或回复> [原因] — 警告用户（回复消息时会自动删除该消息）
/warns <用户ID或回复> — 查看警告记录
/resetwarns <用户ID或回复> — 清除警告

━━━ 🔗 邀请链接 ━━━
/invite [过期分钟] [使用次数] — 管理员创建邀请链接
/invite — 普通用户创建邀请链接（需管理员授权）
/set_invite all [次数] — 允许所有用户邀请（默认1人）
/set_invite <用户ID> [次数] — 允许特定用户邀请（默认1人）
/set_invite off — 关闭所有普通用户邀请权限
/set_invite off <用户ID> — 关闭特定用户邀请权限
/set_invite list — 查看当前邀请权限配置
/invites — 查看邀请链接列表
/revoke <链接> — 撤销邀请链接
/whoinvited <用户ID或回复> — 查看邀请来源

━━━ 🛡️ 管理员管理 ━━━
/setadmin — 设置管理员（输入查看详细帮助）
  /setadmin bot <用户ID或回复> [权限...] — 设置 Bot 命令权限
  /setadmin tg <用户ID或回复> [权限...] — 设置 TG 群组管理员
  /setadmin off <用户ID或回复> — 彻底移除管理员
  Bot 权限：kick, ban, mute, warn, delete, pin, invite, admin, config, blacklist, filter, logs, announce, note
  TG 权限：manage, delete, restrict, invite, pin, video, promote, info, topics
  例：/setadmin bot 123456 all — 全部 Bot 权限
  例：/setadmin bot 123456 kick warn — 只有踢出和警告
  例：/setadmin tg 123456 all — 全部 TG 管理权限
  例：/setadmin tg 123456 delete pin — 只能删消息和置顶
  例：/setadmin off 123456 — 移除所有管理员身份
/admins — 查看管理员列表

━━━ 🔑 权限管理 ━━━
可用权限列表：
  kick — 踢出用户
  ban — 封禁/解封
  mute — 禁言/解禁
  warn — 警告
  delete — 删除消息
  pin — 置顶/取消置顶
  invite — 管理邀请链接
  admin — 管理其他管理员
  config — 修改群组配置
  blacklist — 黑名单管理
  filter — 敏感词管理
  logs — 查看操作日志
  announce — 发布群公告
  note — 用户备注/标签

/addperm <用户ID> <权限...> — 追加权限
  例：/addperm 123456 kick ban
/delperm <用户ID> <权限...> — 移除权限
  例：/delperm 123456 ban
/perms <用户ID> — 查看用户权限详情

━━━ 📝 消息管理 ━━━
/del — 删除回复的消息
/pin — 置顶回复的消息
/unpin — 取消置顶
/unpinall — 取消所有置顶
/announce <内容> — 发布群公告

━━━ ⚙️ 配置与信息 ━━━
/settings — 查看群组当前配置
/setconfig <配置项> <值> — 修改配置
  可用配置项：
  warn_limit <数字> — 警告上限（默认3，达到自动踢）
  new_user_mute_minutes <数字> — 新用户静默期分钟（默认5，0关闭）
  flood_messages <数字> — 洪水检测消息数（默认5）
  flood_seconds <数字> — 洪水检测时间窗秒数（默认5）
  link_filter <true/false> — 链接过滤（默认false）
  media_filter <true/false> — 媒体过滤（默认false）
  forward_filter <true/false> — 转发过滤（默认false）
  welcome_enabled <true/false> — 欢迎消息（默认true）
  welcome_text <文本> — 欢迎消息模板（{user} {chat}）
  goodbye_enabled <true/false> — 告别消息（默认false）
  goodbye_text <文本> — 告别消息模板
  captcha_enabled <true/false> — 入群验证（默认true）
  captcha_timeout <数字> — 验证超时秒数（默认120）
  auto_delete_seconds <数字> — 自动删除消息秒数（默认0关闭）
  例：/setconfig link_filter true
  例：/setconfig warn_limit 5
  例：/setconfig welcome_text 欢迎 {user} 加入！
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
/addword <词语> — 添加敏感词（三种模式）
  普通模式：子串匹配
    例：/addword 禁止
  通配符模式：* 匹配任意字符，? 匹配单个字符
    例：/addword bad* — 匹配 bad, badword 等
    例：/addword te?t — 匹配 test, text 等
  正则模式：re: 开头使用正则表达式
    例：/addword re:\\w+_[pvd]:\\w{32}
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
