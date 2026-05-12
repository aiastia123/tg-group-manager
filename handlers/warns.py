"""警告系统"""
from telegram import Update
from telegram.ext import ContextTypes
from utils.decorators import admin_required, require_perm
from utils.private_reply import reply_private
from services import database as db


@require_perm("warn")
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """警告用户：/warn @user [原因]"""
    target = await _get_target(update, context)
    if not target:
        return

    reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    chat_id = update.effective_chat.id
    warn_limit = db.get_settings(chat_id)["warn_limit"]

    count = db.add_warn(chat_id, target.id, reason, update.effective_user.id)
    display = target.username or target.first_name

    detail = f"警告 {display} ({count}/{warn_limit})" + (f"，原因：{reason}" if reason else "")
    db.add_log(chat_id, update.effective_user.id, "warn", target.id, detail)

    if count >= warn_limit:
        # 自动踢出
        try:
            await context.bot.ban_chat_member(chat_id, target.id)
            await context.bot.unban_chat_member(chat_id, target.id)
            db.clear_warns(chat_id, target.id)
            db.add_log(chat_id, update.effective_user.id, "auto_kick", target.id,
                       f"警告满 {warn_limit} 次自动踢出 {display}")
            await update.effective_message.reply_text(
                f"⚠️ {display} 已达 {warn_limit} 次警告上限，已自动踢出"
            )
        except Exception as e:
            await update.effective_message.reply_text(f"❌ 自动踢出失败：{e}")
    else:
        msg = f"⚠️ {display} 收到警告 ({count}/{warn_limit})"
        if reason:
            msg += f"\n原因：{reason}"
        await update.effective_message.reply_text(msg)


@admin_required
async def warns_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看警告：/warns @user"""
    target = await _get_target(update, context)
    if not target:
        return

    chat_id = update.effective_chat.id
    warns = db.get_warns(chat_id, target.id)
    display = target.username or target.first_name
    warn_limit = db.get_settings(chat_id)["warn_limit"]

    if not warns:
        await update.effective_message.reply_text(f"✅ {display} 没有警告记录")
        return

    msg = f"📋 {display} 的警告记录 ({len(warns)}/{warn_limit})：\n"
    for i, w in enumerate(warns, 1):
        reason = w["reason"] or "无原因"
        msg += f"  {i}. {reason}\n"

    await reply_private(update, context, msg, f"📋 {display} 的警告记录已准备好，点击下方按钮私聊查看", "⚠️ 点击查看警告")


@require_perm("warn")
async def reset_warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """清除警告：/resetwarns @user"""
    target = await _get_target(update, context)
    if not target:
        return

    chat_id = update.effective_chat.id
    count = db.clear_warns(chat_id, target.id)
    display = target.username or target.first_name
    db.add_log(chat_id, update.effective_user.id, "reset_warns", target.id, f"清除 {display} 的 {count} 条警告")
    await update.effective_message.reply_text(f"✅ 已清除 {display} 的 {count} 条警告")


async def _get_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """获取目标用户"""
    # 优先从回复消息获取
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user

    # 从参数获取 user_id
    if context.args:
        try:
            uid = int(context.args[0])
            member = await context.bot.get_chat_member(update.effective_chat.id, uid)
            return member.user if hasattr(member, 'user') else member
        except (ValueError, Exception):
            pass

    await update.effective_message.reply_text(
        "❌ 请回复目标用户的消息，或提供用户 ID"
    )
    return None
