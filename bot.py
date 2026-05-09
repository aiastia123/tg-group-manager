"""Telegram 群组管理 Bot — 主入口"""
import logging
import os
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
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
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    if not BOT_TOKEN:
        print("❌ 请设置环境变量 BOT_TOKEN")
        return

    # 初始化数据库
    init_db()
    logger.info("数据库初始化完成")

    app = Application.builder().token(BOT_TOKEN).build()

    # ─── 注册命令 ───

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

    # 启动
    logger.info("Bot 启动中...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
