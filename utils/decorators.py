"""权限检查工具"""
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from services.database import is_custom_admin


async def is_bot_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """检查 bot 是否是群管理员"""
    if not update.effective_chat:
        return False
    bot_member = await update.effective_chat.get_member(context.bot.id)
    return bot_member.status in ("administrator", "creator")


async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> bool:
    """检查用户是否是群管理员（TG原生 或 bot自定义）"""
    if not update.effective_chat:
        return False
    uid = user_id or update.effective_user.id
    member = await update.effective_chat.get_member(uid)
    if member.status in ("administrator", "creator"):
        return True
    # 检查自定义管理员
    return is_custom_admin(update.effective_chat.id, uid)


def admin_required(func):
    """装饰器：仅管理员可用"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user:
            return
        if not await is_user_admin(update, context):
            await update.effective_message.reply_text("⛔ 此命令仅管理员可用")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def private_chat_only(func):
    """装饰器：仅私聊可用"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_chat and update.effective_chat.type != "private":
            return
        return await func(update, context, *args, **kwargs)
    return wrapper
