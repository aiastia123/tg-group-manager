"""Telegram 群组管理 Bot — 主入口"""
import asyncio
import logging
import os
from telegram import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from config import BOT_TOKEN
from services.database import init_db, cleanup_expired_captchas, cleanup_expired_mutes
from handlers import (
    user_management,
    warns,
    invites,
    admin_management,
    messages,
    captcha_welcome,
    settings_and_info,
    filters as msg_filters,
    help_handler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# 群内命令和回复自动删除时间（秒）
AUTO_DELETE_DELAY = 30


async def auto_delete(context: ContextTypes.DEFAULT_TYPE):
    """自动删除群里的命令消息和 bot 回复"""
    for msg_id in context.job.data:
        try:
            await context.bot.delete_message(context.job.chat_id, msg_id)
        except Exception:
            pass


async def post_init(application):
    """Bot 初始化后：注册命令菜单"""
    # 私聊命令菜单
    private_commands = [
        BotCommand("start", "启动 bot / 获取邀请链接"),
        BotCommand("help", "查看帮助信息"),
    ]
    await application.bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())

    # 群聊命令菜单
    group_commands = [
        BotCommand("help", "查看帮助"),
        BotCommand("report", "举报用户"),
        BotCommand("kick", "踢出用户"),
        BotCommand("ban", "封禁用户"),
        BotCommand("tempban", "临时封禁"),
        BotCommand("unban", "解封用户"),
        BotCommand("mute", "禁言用户"),
        BotCommand("unmute", "解除禁言"),
        BotCommand("warn", "警告用户"),
        BotCommand("warns", "查看警告"),
        BotCommand("resetwarns", "清除警告"),
        BotCommand("invite", "创建邀请链接"),
        BotCommand("invites", "邀请链接列表"),
        BotCommand("revoke", "撤销邀请链接"),
        BotCommand("del", "删除消息"),
        BotCommand("pin", "置顶消息"),
        BotCommand("unpin", "取消置顶"),
        BotCommand("settings", "群组设置"),
        BotCommand("rules", "查看群规"),
        BotCommand("info", "用户信息"),
        BotCommand("admins", "管理员列表"),
        BotCommand("blacklist", "黑名单管理"),
        BotCommand("blacklists", "查看黑名单"),
        BotCommand("words", "敏感词列表"),
        BotCommand("logs", "操作日志"),
    ]
    await application.bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())
    logger.info("Bot 命令菜单已注册")


def main():
    if not BOT_TOKEN:
        print("❌ 请设置环境变量 BOT_TOKEN")
        return

    # 初始化数据库
    init_db()
    logger.info("数据库初始化完成")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # ─── 注册命令 ───

    # 帮助与启动
    app.add_handler(CommandHandler("start", help_handler.start_command))
    app.add_handler(CommandHandler("help", help_handler.help_command))

    # 用户管理
    app.add_handler(CommandHandler("kick", user_management.kick_user))
    app.add_handler(CommandHandler("ban", user_management.ban_user))
    app.add_handler(CommandHandler("tempban", user_management.temp_ban))
    app.add_handler(CommandHandler("unban", user_management.unban_user))
    app.add_handler(CommandHandler("mute", user_management.mute_user))
    app.add_handler(CommandHandler("unmute", user_management.unmute_user))

    # 警告系统
    app.add_handler(CommandHandler("warn", warns.warn_user))
    app.add_handler(CommandHandler("warns", warns.warns_list))
    app.add_handler(CommandHandler("resetwarns", warns.reset_warns))

    # 邀请链接
    app.add_handler(CommandHandler("invite", invites.create_invite))
    app.add_handler(CommandHandler("invites", invites.list_invites))
    app.add_handler(CommandHandler("revoke", invites.revoke_invite))
    app.add_handler(CommandHandler("whoinvited", invites.invite_tracking))

    # 管理员
    app.add_handler(CommandHandler("setadmin", admin_management.set_admin))
    app.add_handler(CommandHandler("removeadmin", admin_management.remove_admin))
    app.add_handler(CommandHandler("admins", admin_management.list_admins))
    app.add_handler(CommandHandler("addperm", admin_management.add_perm))
    app.add_handler(CommandHandler("delperm", admin_management.del_perm))
    app.add_handler(CommandHandler("perms", admin_management.show_perms))

    # 消息管理
    app.add_handler(CommandHandler("del", messages.delete_message))
    app.add_handler(CommandHandler("pin", messages.pin_message))
    app.add_handler(CommandHandler("unpin", messages.unpin_message))
    app.add_handler(CommandHandler("unpinall", messages.unpin_all))
    app.add_handler(CommandHandler("announce", messages.announce))

    # 配置与信息
    app.add_handler(CommandHandler("setrules", settings_and_info.set_rules))
    app.add_handler(CommandHandler("rules", settings_and_info.show_rules))
    app.add_handler(CommandHandler("settings", settings_and_info.settings_menu))
    app.add_handler(CommandHandler("setconfig", settings_and_info.set_config))
    app.add_handler(CommandHandler("info", settings_and_info.user_info))
    app.add_handler(CommandHandler("note", settings_and_info.set_note))
    app.add_handler(CommandHandler("tags", settings_and_info.set_tags))
    app.add_handler(CommandHandler("blacklist", settings_and_info.add_to_blacklist))
    app.add_handler(CommandHandler("unblacklist", settings_and_info.remove_from_blacklist))
    app.add_handler(CommandHandler("blacklists", settings_and_info.show_blacklist))
    app.add_handler(CommandHandler("logs", settings_and_info.show_logs))

    # 敏感词
    app.add_handler(CommandHandler("addword", settings_and_info.add_word))
    app.add_handler(CommandHandler("delword", settings_and_info.remove_word))
    app.add_handler(CommandHandler("words", settings_and_info.list_words))

    # 举报
    app.add_handler(CommandHandler("report", settings_and_info.report_user))
    app.add_handler(CommandHandler("reports", settings_and_info.show_reports))
    app.add_handler(CommandHandler("resolve", settings_and_info.resolve_report))

    # 入群/退群
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, captcha_welcome.on_new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, captcha_welcome.on_left_member))

    # 验证码按钮回调
    app.add_handler(CallbackQueryHandler(captcha_welcome.handle_captcha_button, pattern=r"^captcha_"))

    # 消息过滤（低优先级，放最后）
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND & ~filters.StatusUpdate.ALL,
        msg_filters.filter_messages,
    ))

    # ─── 群内命令自动删除（group=1 与 group=0 的命令处理器并行执行）───
    async def _delayed_delete(bot, chat_id, msg_id, delay):
        await asyncio.sleep(delay)
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    async def auto_delete_group_command(update, context):
        """自动删除群内的命令消息"""
        if update.effective_chat and update.effective_chat.type != "private" and update.message:
            asyncio.create_task(
                _delayed_delete(
                    context.bot, update.effective_chat.id,
                    update.message.message_id, AUTO_DELETE_DELAY,
                )
            )

    app.add_handler(
        MessageHandler(filters.COMMAND & filters.ChatType.GROUPS, auto_delete_group_command),
        group=1,
    )

    # ─── 启动 ───
    logger.info("Bot 启动中...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()