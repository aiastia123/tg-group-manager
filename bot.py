"""Telegram 群组管理 Bot — 主入口"""
import logging
import os
from telegram import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from config import BOT_TOKEN
from services.database import init_db, cleanup_expired_captchas, cleanup_expired_mutes, cleanup_pending_messages, cleanup_expired_blacklist
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
from utils.decorators import auto_delete_in_group

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


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
        BotCommand("set_invite", "设置邀请权限"),
        BotCommand("invites", "邀请链接列表"),
        BotCommand("revoke", "撤销邀请链接"),
        BotCommand("del", "删除消息"),
        BotCommand("pin", "置顶消息"),
        BotCommand("unpin", "取消置顶"),
        BotCommand("settings", "群组设置"),
        BotCommand("rules", "查看群规"),
        BotCommand("info", "用户信息"),
        BotCommand("setadmin", "设置管理员"),
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

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).concurrent_updates(True).build()

    # ─── 全局错误处理器：确保 handler 异常不被静默吞掉 ───
    async def _error_handler(update, context):
        logger.error(f"处理 update 时发生未捕获异常: {context.error}", exc_info=context.error)
    app.add_error_handler(_error_handler)

    # ─── 临时诊断：记录收到的群事件类型（排查入群事件是否到达 Bot） ───
    async def _log_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message and update.message.new_chat_members:
            logger.info(f"[诊断] 收到 new_chat_members 事件，来自 chat={update.effective_chat.id}")
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, _log_update), group=-1)

    # ─── 辅助函数：注册带自动删除的命令 ───
    def add_cmd(name, handler, keep_bot_reply=False):
        """注册命令，自动包装 auto_delete_in_group 装饰器

        Args:
            keep_bot_reply: 为 True 时只删除用户命令消息，保留 bot 的回复。
                适用于 /warn、/mute、/rules 等需要让用户看到回复的命令。
        """
        wrapped = auto_delete_in_group(handler, delete_bot_replies=not keep_bot_reply)
        app.add_handler(CommandHandler(name, wrapped))

    # ─── 注册命令 ───

    # 帮助与启动（不需要自动删除）
    app.add_handler(CommandHandler("start", help_handler.start_command))
    app.add_handler(CommandHandler("help", help_handler.help_command))
    # 诊断命令：查看群组类型与 ID
    app.add_handler(CommandHandler("chatinfo", help_handler.chatinfo_command))

    # 用户管理（mute/unmute 需要保留 bot 回复，让被操作用户看到）
    add_cmd("kick", user_management.kick_user)
    add_cmd("ban", user_management.ban_user)
    add_cmd("tempban", user_management.temp_ban)
    add_cmd("unban", user_management.unban_user)
    add_cmd("mute", user_management.mute_user, keep_bot_reply=True)
    add_cmd("unmute", user_management.unmute_user, keep_bot_reply=True)

    # 警告系统（/warn 需要保留 bot 回复，让被警告用户看到）
    add_cmd("warn", warns.warn_user, keep_bot_reply=True)
    add_cmd("warns", warns.warns_list)
    add_cmd("resetwarns", warns.reset_warns)

    # 邀请链接
    add_cmd("invite", invites.create_invite)
    add_cmd("set_invite", invites.set_invite_perm)
    add_cmd("invites", invites.list_invites)
    add_cmd("revoke", invites.revoke_invite)
    add_cmd("whoinvited", invites.invite_tracking)

    # 管理员
    add_cmd("setadmin", admin_management.set_admin)
    add_cmd("admins", admin_management.list_admins)
    add_cmd("addperm", admin_management.add_perm)
    add_cmd("delperm", admin_management.del_perm)
    add_cmd("perms", admin_management.show_perms)

    # 消息管理（/announce 发布的公告需要保留）
    add_cmd("del", messages.delete_message)
    add_cmd("pin", messages.pin_message)
    add_cmd("unpin", messages.unpin_message)
    add_cmd("unpinall", messages.unpin_all)
    add_cmd("announce", messages.announce, keep_bot_reply=True)

    # 配置与信息（/rules 群规需要保留供用户查看）
    add_cmd("setrules", settings_and_info.set_rules)
    add_cmd("rules", settings_and_info.show_rules, keep_bot_reply=True)
    add_cmd("settings", settings_and_info.settings_menu)
    add_cmd("setconfig", settings_and_info.set_config)
    add_cmd("info", settings_and_info.user_info)
    add_cmd("note", settings_and_info.set_note)
    add_cmd("tags", settings_and_info.set_tags)
    add_cmd("blacklist", settings_and_info.add_to_blacklist)
    add_cmd("unblacklist", settings_and_info.remove_from_blacklist)
    add_cmd("blacklists", settings_and_info.show_blacklist)
    add_cmd("logs", settings_and_info.show_logs)

    # 敏感词
    add_cmd("addword", settings_and_info.add_word)
    add_cmd("delword", settings_and_info.remove_word)
    add_cmd("words", settings_and_info.list_words)

    # 举报（举报者需要看到确认信息）
    add_cmd("report", settings_and_info.report_user, keep_bot_reply=True)
    add_cmd("reports", settings_and_info.show_reports)
    add_cmd("resolve", settings_and_info.resolve_report)

    # 入群/退群
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, captcha_welcome.on_new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, captcha_welcome.on_left_member))

    # 验证码按钮回调
    app.add_handler(CallbackQueryHandler(captcha_welcome.handle_captcha_button, pattern=r"^captcha_"))

    # 私聊消息处理（验证码答案）— 放在群消息过滤器之前
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.COMMAND,
        captcha_welcome.handle_captcha_answer,
    ))

    # 消息过滤（低优先级，放最后）
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND & ~filters.StatusUpdate.ALL,
        msg_filters.filter_messages,
    ))

    # ─── 定时清理任务（每小时清理已领取/过期的临时数据） ───
    async def _cleanup_job(context):
        try:
            cleanup_expired_captchas()
            cleanup_expired_mutes()
            cleanup_pending_messages()
            # 清理过期黑名单，并同步解除 Telegram 侧封禁
            expired = cleanup_expired_blacklist()
            if expired:
                for chat_id, user_id in expired:
                    try:
                        await context.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
                    except Exception as e:
                        logger.warning(f"自动解封 {user_id} in {chat_id} 失败: {e}")
                logger.info(f"清理了 {len(expired)} 条过期黑名单记录并同步 Telegram 解封")
            logger.info("定时清理完成")
        except Exception as e:
            logger.error(f"定时清理失败：{e}")

    app.job_queue.run_once(_cleanup_job, 10)       # 启动 10 秒后清理一次
    app.job_queue.run_repeating(_cleanup_job, 3600)  # 之后每小时清理一次

    # ─── 启动 ───
    logger.info("Bot 启动中...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()