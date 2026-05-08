"""管理员设置"""
from telegram import Update, ChatAdministratorRights, ChatMemberAdministrator
from telegram.ext import ContextTypes
from utils.decorators import admin_required
from services import database as db


@admin_required
async def set_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置管理员：/setadmin @user"""
    target = await _get_target(update, context)
    if not target:
        return

    chat_id = update.effective_chat.id

    # 检查调用者是否是群主（只有群主能设置 TG 管理员）
    caller = await update.effective_chat.get_member(update.effective_user.id)
    if caller.status != "creator":
        # 非 TG 群主 → 添加为自定义管理员
        db.add_custom_admin(chat_id, target.id, update.effective_user.id)
        display = target.username or target.first_name
        db.add_log(chat_id, update.effective_user.id, "set_admin", target.id,
                   f"设置 {display} 为自定义管理员")
        await update.effective_message.reply_text(
            f"✅ {display} 已设为自定义管理员（Bot管理员）\n"
            "注：TG 群主可使用 /setadmin 提升为 TG 原生管理员"
        )
        return

    # TG 群主 → 提升为 TG 管理员
    try:
        rights = ChatAdministratorRights(
            is_anonymous=False,
            can_manage_chat=True,
            can_delete_messages=True,
            can_manage_video_chats=True,
            can_restrict_members=True,
            can_promote_members=False,
            can_change_info=True,
            can_invite_users=True,
            can_post_messages=True,
            can_edit_messages=True,
            can_pin_messages=True,
            can_manage_topics=True,
        )
        await context.bot.promote_chat_member(chat_id, target.id, can_manage_chat=True,
                                               can_delete_messages=True, can_restrict_members=True,
                                               can_invite_users=True, can_pin_messages=True)
        display = target.username or target.first_name
        db.add_custom_admin(chat_id, target.id, update.effective_user.id)
        db.add_log(chat_id, update.effective_user.id, "set_admin", target.id,
                   f"设置 {display} 为 TG 管理员")
        await update.effective_message.reply_text(f"✅ {display} 已设为管理员")
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 设置管理员失败：{e}")


@admin_required
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消管理员：/removeadmin @user"""
    target = await _get_target(update, context)
    if not target:
        return

    chat_id = update.effective_chat.id
    display = target.username or target.first_name

    # 尝试移除 TG 管理员
    try:
        await context.bot.promote_chat_member(
            chat_id, target.id,
            is_anonymous=False,
            can_manage_chat=False,
            can_delete_messages=False,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_promote_members=False,
            can_change_info=False,
            can_invite_users=False,
            can_post_messages=False,
            can_edit_messages=False,
            can_pin_messages=False,
            can_manage_topics=False,
        )
    except Exception:
        pass

    db.remove_custom_admin(chat_id, target.id)
    db.add_log(chat_id, update.effective_user.id, "remove_admin", target.id,
               f"取消 {display} 的管理员")
    await update.effective_message.reply_text(f"✅ 已取消 {display} 的管理员")


@admin_required
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看管理员列表：/admins"""
    chat_id = update.effective_chat.id
    custom = db.get_custom_admins(chat_id)

    # 获取 TG 管理员
    administrators = await context.bot.get_chat_administrators(chat_id)
    msg = "📋 管理员列表：\n\n"
    msg += "🔹 TG 管理员：\n"
    for admin in administrators:
        user = admin.user
        name = user.username or user.first_name
        role = "群主" if admin.status == "creator" else "管理员"
        msg += f"  • {name} ({role})\n"

    if custom:
        msg += "\n🔹 Bot 管理员：\n"
        for a in custom:
            try:
                member = await context.bot.get_chat_member(chat_id, a["user_id"])
                name = member.user.username or member.user.first_name
            except Exception:
                name = str(a["user_id"])
            msg += f"  • {name}\n"

    await update.effective_message.reply_text(msg)


async def _get_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    if context.args:
        try:
            uid = int(context.args[0])
            member = await context.bot.get_chat_member(update.effective_chat.id, uid)
            return member.user if hasattr(member, 'user') else member
        except (ValueError, Exception):
            pass
    await update.effective_message.reply_text("❌ 请回复目标用户的消息，或提供用户 ID")
    return None
