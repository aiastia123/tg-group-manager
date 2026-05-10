"""邀请链接管理"""
import time
from telegram import Update
from telegram.ext import ContextTypes
from utils.decorators import admin_required, require_perm
from services import database as db


@require_perm("invite")
async def create_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """创建邀请链接：/invite [过期分钟] [使用次数]"""
    expire_minutes = 0
    member_limit = 0

    if len(context.args) >= 1:
        try:
            expire_minutes = int(context.args[0])
        except ValueError:
            await update.effective_message.reply_text("❌ 过期时间必须是数字（分钟）")
            return
    if len(context.args) >= 2:
        try:
            member_limit = int(context.args[1])
        except ValueError:
            await update.effective_message.reply_text("❌ 使用次数必须是数字")
            return

    chat_id = update.effective_chat.id
    invite_link = await context.bot.create_chat_invite_link(
        chat_id,
        expire_date=int(time.time()) + expire_minutes * 60 if expire_minutes > 0 else None,
        member_limit=member_limit if member_limit > 0 else None,
    )

    db.save_invite_link(
        chat_id,
        invite_link.invite_link,
        update.effective_user.id,
        expires_at=invite_link.expire_date.timestamp() if invite_link.expire_date else 0,
        member_limit=member_limit,
    )
    db.add_log(chat_id, update.effective_user.id, "create_invite", details=f"创建邀请链接 {invite_link.invite_link}")

    # 构建邀请链接消息
    msg = f"✅ 邀请链接已创建：\n{invite_link.invite_link}"
    if expire_minutes:
        msg += f"\n有效期：{expire_minutes} 分钟"
    if member_limit:
        msg += f"\n使用次数：{member_limit}"

    # 通过私聊发送给管理员
    try:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=msg,
        )
        # 群内只回复确认，不暴露链接
        await update.effective_message.reply_text("✅ 邀请链接已通过私聊发送给你")
    except Exception:
        # 如果私聊失败（用户未启动 bot），退回到群内发送
        await update.effective_message.reply_text(
            msg + "\n\n⚠️ 私聊发送失败，请先私聊 bot 发送 /start 以启动对话"
        )


@require_perm("invite")
async def list_invites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看邀请链接：/invites"""
    chat_id = update.effective_chat.id
    links = db.get_invite_links(chat_id)

    if not links:
        await update.effective_message.reply_text("📭 没有邀请链接记录")
        return

    msg = "📋 邀请链接列表：\n\n"
    for i, link in enumerate(links[:10], 1):
        status = "🟢" if link["active"] else "🔴"
        msg += f"{i}. {status} {link['link']}\n"
        if link["member_limit"]:
            msg += f"   使用次数：{link['usage_count']}/{link['member_limit']}\n"

    await update.effective_message.reply_text(msg)


@require_perm("invite")
async def revoke_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """撤销邀请链接：/revoke <链接>"""
    if not context.args:
        await update.effective_message.reply_text("用法：/revoke <邀请链接>")
        return

    link = context.args[0]
    chat_id = update.effective_chat.id

    try:
        await context.bot.revoke_chat_invite_link(chat_id, link)
        db.deactivate_invite_link(chat_id, link)
        db.add_log(chat_id, update.effective_user.id, "revoke_invite", details=f"撤销邀请链接 {link}")
        await update.effective_message.reply_text("✅ 邀请链接已撤销")
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 撤销失败：{e}")


@require_perm("invite")
async def invite_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看谁邀请了谁：/whoinvited @user"""
    target = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    elif context.args:
        try:
            uid = int(context.args[0])
            member = await context.bot.get_chat_member(update.effective_chat.id, uid)
            target = member.user if hasattr(member, 'user') else member
        except (ValueError, Exception):
            pass

    if not target:
        await update.effective_message.reply_text("用法：/whoinvited <用户ID或回复消息>")
        return

    chat_id = update.effective_chat.id
    info = db.get_invite_tracking(chat_id, target.id)
    display = target.username or target.first_name

    if not info:
        await update.effective_message.reply_text(f"📭 没有找到 {display} 的邀请记录")
        return

    msg = f"📋 {display} 的邀请信息：\n"
    if info["inviter_id"]:
        try:
            inviter = await context.bot.get_chat_member(chat_id, info["inviter_id"])
            inviter_name = inviter.user.username or inviter.user.first_name
            msg += f"邀请人：{inviter_name}\n"
        except Exception:
            msg += f"邀请人ID：{info['inviter_id']}\n"
    if info["link"]:
        msg += f"邀请链接：{info['link']}\n"

    await update.effective_message.reply_text(msg)
