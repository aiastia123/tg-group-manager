"""用户管理：踢出、封禁、临时封禁、禁言、解禁"""
import time
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from utils.decorators import admin_required, require_perm
from services import database as db


@require_perm("kick")
async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """踢出用户：/kick @user [原因] 或回复消息"""
    try:
        target = await _resolve_user(update, context)
        if not target:
            return
    except Exception:
        await update.effective_message.reply_text("❌ 找不到该用户")
        return

    # 回复消息时，参数全部作为原因；否则跳过第一个参数（用户标识）
    if update.message.reply_to_message:
        reason = " ".join(context.args) if context.args else ""
    else:
        reason = " ".join(context.args[1:]) if context.args and len(context.args) > 1 else ""
    chat_id = update.effective_chat.id

    try:
        await context.bot.ban_chat_member(chat_id, target.id)
        # 立即解除封禁（变相踢出，允许重新加入）
        await context.bot.unban_chat_member(chat_id, target.id)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 踢出失败：{e}")
        return

    display = target.username or target.first_name
    detail = f"踢出 {display}" + (f"，原因：{reason}" if reason else "")
    db.add_log(chat_id, update.effective_user.id, "kick", target.id, detail)

    msg = f"✅ 已踢出 {display}"
    if reason:
        msg += f"\n原因：{reason}"
    await update.effective_message.reply_text(msg)


@require_perm("ban")
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """封禁用户：/ban @user [原因] 或回复消息"""
    try:
        target = await _resolve_user(update, context)
        if not target:
            return
    except Exception:
        await update.effective_message.reply_text("❌ 找不到该用户")
        return

    # 回复消息时，参数全部作为原因；否则跳过第一个参数（用户标识）
    if update.message.reply_to_message:
        reason = " ".join(context.args) if context.args else ""
    else:
        reason = " ".join(context.args[1:]) if context.args and len(context.args) > 1 else ""
    chat_id = update.effective_chat.id

    try:
        await context.bot.ban_chat_member(chat_id, target.id)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 封禁失败：{e}")
        return

    display = target.username or target.first_name
    detail = f"封禁 {display}" + (f"，原因：{reason}" if reason else "")
    db.add_log(chat_id, update.effective_user.id, "ban", target.id, detail)

    msg = f"✅ 已封禁 {display}"
    if reason:
        msg += f"\n原因：{reason}"
    await update.effective_message.reply_text(msg)


@require_perm("ban")
async def temp_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """临时封禁：/tempban @user <分钟> [原因] 或回复消息 <分钟> [原因]"""
    # 回复消息时，第一个参数是分钟数；否则需要至少2个参数
    if update.message.reply_to_message:
        if not context.args:
            await update.effective_message.reply_text("用法：回复消息 /tempban <分钟数> [原因]")
            return
        try:
            minutes = int(context.args[0])
        except ValueError:
            await update.effective_message.reply_text("❌ 分钟数必须是数字")
            return
    else:
        if len(context.args) < 2:
            await update.effective_message.reply_text("用法：/tempban @用户 <分钟数> [原因]")
            return
        try:
            minutes = int(context.args[1])
        except ValueError:
            await update.effective_message.reply_text("❌ 分钟数必须是数字")
            return

    try:
        target = await _resolve_user(update, context)
        if not target:
            return
    except Exception:
        await update.effective_message.reply_text("❌ 找不到该用户")
        return

    # 回复消息时，原因从第二个参数开始；否则从第三个参数开始
    if update.message.reply_to_message:
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    else:
        reason = " ".join(context.args[2:]) if len(context.args) > 2 else ""
    chat_id = update.effective_chat.id
    until = int(time.time()) + minutes * 60

    try:
        await context.bot.ban_chat_member(chat_id, target.id, until_date=until)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 临时封禁失败：{e}")
        return

    display = target.username or target.first_name
    detail = f"临时封禁 {display} {minutes}分钟" + (f"，原因：{reason}" if reason else "")
    db.add_log(chat_id, update.effective_user.id, "temp_ban", target.id, detail)

    await update.effective_message.reply_text(
        f"✅ 已临时封禁 {display}，{minutes}分钟后自动解封"
    )


@require_perm("ban")
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """解封用户：/unban @user 或回复消息"""
    try:
        target = await _resolve_user(update, context)
        if not target:
            return
    except Exception:
        await update.effective_message.reply_text("❌ 找不到该用户")
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.unban_chat_member(chat_id, target.id)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 解封失败：{e}")
        return

    display = target.username or target.first_name
    db.add_log(chat_id, update.effective_user.id, "unban", target.id, f"解封 {display}")
    await update.effective_message.reply_text(f"✅ 已解封 {display}")


@require_perm("mute")
async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """禁言用户：/mute @user [分钟] 或回复消息"""
    try:
        target = await _resolve_user(update, context)
        if not target:
            return
    except Exception:
        await update.effective_message.reply_text("❌ 找不到该用户")
        return

    minutes = 60
    # 回复消息时，第一个参数是分钟数；否则第二个参数是分钟数
    if update.message.reply_to_message:
        if context.args:
            try:
                minutes = int(context.args[0])
            except ValueError:
                await update.effective_message.reply_text("❌ 分钟数必须是数字")
                return
    else:
        if len(context.args) > 1:
            try:
                minutes = int(context.args[1])
            except ValueError:
                await update.effective_message.reply_text("❌ 分钟数必须是数字")
                return

    chat_id = update.effective_chat.id
    until = time.time() + minutes * 60

    try:
        await context.bot.restrict_chat_member(
            chat_id, target.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
                can_manage_topics=False,
            ),
            until_date=int(until),
        )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 禁言失败：{e}")
        return

    db.add_mute(chat_id, target.id, until)
    display = target.username or target.first_name
    db.add_log(chat_id, update.effective_user.id, "mute", target.id, f"禁言 {display} {minutes}分钟")
    await update.effective_message.reply_text(f"✅ 已禁言 {display}，{minutes}分钟后自动解除")


@require_perm("mute")
async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """解除禁言：/unmute @user 或回复消息"""
    try:
        target = await _resolve_user(update, context)
        if not target:
            return
    except Exception:
        await update.effective_message.reply_text("❌ 找不到该用户")
        return

    chat_id = update.effective_chat.id
    try:
        # 使用群默认权限来清除例外列表中的记录
        chat_info = await context.bot.get_chat(chat_id)
        await context.bot.restrict_chat_member(
            chat_id, target.id,
            permissions=chat_info.permissions,
        )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 解除禁言失败：{e}")
        return

    db.remove_mute(chat_id, target.id)
    display = target.username or target.first_name
    db.add_log(chat_id, update.effective_user.id, "unmute", target.id, f"解除禁言 {display}")
    await update.effective_message.reply_text(f"✅ 已解除 {display} 的禁言")


# ─── 辅助函数 ───

async def _resolve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """从命令参数中解析用户（@username、回复消息、或 user_id）"""
    # 尝试从回复消息获取
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user

    # 尝试从参数解析
    if context.args:
        arg = context.args[0]
        # @username
        if arg.startswith("@"):
            username = arg[1:]
            # python-telegram-bot 没有直接的 get_chat_member_by_username
            # 尝试通过回复或已知成员查找，这里用 try-except
            return None  # 需要用户 ID，提示用户回复消息
        # user_id
        try:
            uid = int(arg)
            member = await context.bot.get_chat_member(update.effective_chat.id, uid)
            return member.user  # 统一返回 User 对象
        except (ValueError, Exception):
            pass

    await update.effective_message.reply_text(
        "❌ 请回复目标用户的消息，或提供用户 ID\n"
        "用法：/命令 <用户ID或回复消息> [参数]"
    )
    return None
