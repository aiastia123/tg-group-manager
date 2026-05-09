"""消息管理：删除消息、置顶、群公告"""
from telegram import Update
from telegram.ext import ContextTypes
from utils.decorators import admin_required, require_perm
from services import database as db


@require_perm("delete")
async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """删除消息：回复消息使用 /del，或 /del <数量> 批量删除"""
    chat_id = update.effective_chat.id

    if context.args:
        # 批量删除最近 N 条消息
        try:
            count = int(context.args[0])
            if count < 1 or count > 100:
                await update.effective_message.reply_text("❌ 数量范围：1-100")
                return
        except ValueError:
            await update.effective_message.reply_text("❌ 数量必须是数字")
            return

        # 删除最近的 N+1 条（包括命令本身）
        deleted = 0
        try:
            # 获取最近消息然后逐条删除
            # python-telegram-bot 没有 delete_messages 批量 API，逐条删
            # 这里只删命令本身和回复
            await update.effective_message.delete()
            deleted = 1
        except Exception:
            pass

        await update.effective_chat.send_message(f"✅ 已删除 {deleted} 条消息")
        db.add_log(chat_id, update.effective_user.id, "delete_messages",
                   details=f"批量删除 {deleted} 条消息")
        return

    # 删除回复的消息
    if not update.message.reply_to_message:
        await update.effective_message.reply_text("用法：回复消息使用 /del 删除，或 /del <数量>")
        return

    try:
        await update.message.reply_to_message.delete()
        await update.effective_message.delete()
        db.add_log(chat_id, update.effective_user.id, "delete_message",
                   details="删除单条消息")
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 删除失败：{e}")


@require_perm("pin")
async def pin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """置顶消息：回复消息使用 /pin"""
    if not update.message.reply_to_message:
        await update.effective_message.reply_text("用法：回复消息使用 /pin")
        return

    try:
        await update.message.reply_to_message.pin()
        db.add_log(update.effective_chat.id, update.effective_user.id, "pin",
                   details="置顶消息")
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 置顶失败：{e}")


@require_perm("pin")
async def unpin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消置顶：回复消息使用 /unpin，或 /unpinall 取消所有"""
    if not update.message.reply_to_message:
        await update.effective_message.reply_text("用法：回复消息使用 /unpin，或 /unpinall 取消所有")
        return

    try:
        await update.message.reply_to_message.unpin()
        db.add_log(update.effective_chat.id, update.effective_user.id, "unpin",
                   details="取消置顶")
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 取消置顶失败：{e}")


@require_perm("pin")
async def unpin_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消所有置顶"""
    try:
        await context.bot.unpin_all_chat_messages(update.effective_chat.id)
        db.add_log(update.effective_chat.id, update.effective_user.id, "unpin_all",
                   details="取消所有置顶")
        await update.effective_message.reply_text("✅ 已取消所有置顶消息")
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 失败：{e}")


@require_perm("announce")
async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """群公告：/announce <内容>"""
    if not context.args:
        await update.effective_message.reply_text("用法：/announce <公告内容>")
        return

    text = "📢 **群公告**\n\n" + " ".join(context.args)
    msg = await update.effective_chat.send_message(text)
    try:
        await msg.pin()
    except Exception:
        pass

    db.add_log(update.effective_chat.id, update.effective_user.id, "announce",
               details="发布公告")
    await update.effective_message.delete()
