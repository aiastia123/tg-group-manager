"""权限检查工具"""
import asyncio
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from services.database import is_custom_admin, admin_has_permission

# 群内消息自动删除延迟（秒）
AUTO_DELETE_DELAY = 30


async def _delayed_delete(bot, chat_id, msg_id, delay):
    """延迟删除消息"""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


def auto_delete_in_group(func):
    """装饰器：群聊中自动删除用户的命令消息和 bot 的回复"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        # 私聊不处理
        if not update.effective_chat or update.effective_chat.type == "private":
            return await func(update, context, *args, **kwargs)

        chat_id = update.effective_chat.id

        # 包装 reply_text，追踪 bot 回复的消息
        original_reply = update.effective_message.reply_text

        async def tracked_reply(*reply_args, **reply_kwargs):
            msg = await original_reply(*reply_args, **reply_kwargs)
            # 安排删除 bot 回复
            asyncio.create_task(_delayed_delete(context.bot, chat_id, msg.message_id, AUTO_DELETE_DELAY))
            return msg

        update.effective_message.reply_text = tracked_reply

        # 执行原始命令 handler
        await func(update, context, *args, **kwargs)

        # 安排删除用户的命令消息
        asyncio.create_task(_delayed_delete(context.bot, chat_id, update.message.message_id, AUTO_DELETE_DELAY))

    return wrapper


async def _is_tg_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> bool:
    """检查用户是否是 TG 原生管理员（群主/管理员）"""
    if not update.effective_chat:
        return False
    uid = user_id or update.effective_user.id
    member = await update.effective_chat.get_member(uid)
    return member.status in ("administrator", "creator")


async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> bool:
    """检查用户是否是管理员（TG原生 或 bot自定义）"""
    if not update.effective_chat:
        return False
    uid = user_id or update.effective_user.id
    member = await update.effective_chat.get_member(uid)
    if member.status in ("administrator", "creator"):
        return True
    return is_custom_admin(update.effective_chat.id, uid)


async def check_permission(update: Update, context: ContextTypes.DEFAULT_TYPE, perm: str, user_id: int = None) -> bool:
    """
    检查用户是否有某个权限。
    TG 群主/管理员默认拥有全部权限，自定义管理员按分配的权限检查。
    """
    if not update.effective_chat:
        return False
    uid = user_id or update.effective_user.id

    # TG 群主/管理员 → 全部权限
    member = await update.effective_chat.get_member(uid)
    if member.status in ("administrator", "creator"):
        return True

    # 自定义管理员 → 按权限表检查
    if is_custom_admin(update.effective_chat.id, uid):
        return admin_has_permission(update.effective_chat.id, uid, perm)

    return False


# 权限 → 命令的映射
PERM_LABELS = {
    "kick": "踢出",
    "ban": "封禁",
    "mute": "禁言",
    "warn": "警告",
    "delete": "删消息",
    "pin": "置顶",
    "invite": "邀请链接",
    "admin": "管理员管理",
    "config": "群组配置",
    "blacklist": "黑名单",
    "filter": "敏感词",
    "logs": "操作日志",
    "announce": "群公告",
    "note": "用户备注",
}


def require_perm(perm: str):
    """装饰器：检查具体权限"""
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.effective_user:
                return
            if not await check_permission(update, context, perm):
                label = PERM_LABELS.get(perm, perm)
                await update.effective_message.reply_text(f"⛔ 你没有「{label}」权限")
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator


def admin_required(func):
    """装饰器：仅管理员可用（向后兼容，等价于 require_perm 但不检查具体权限）"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user:
            return
        if not await is_user_admin(update, context):
            await update.effective_message.reply_text("⛔ 此命令仅管理员可用")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper
