"""深链私聊回复工具：将敏感信息通过深链按钮发送到私聊"""
import secrets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services import database as db


async def reply_private(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    content: str,
    group_hint: str = "📋 信息已准备好，点击下方按钮私聊查看",
    button_text: str = "📩 点击私聊查看",
):
    """在群聊中发送深链按钮，用户点击后私聊收到完整内容。

    如果已在私聊中，直接发送内容。
    如果在群聊中无法私聊（用户未启动过 bot），降级为群聊回复。
    """
    # 私聊直接发送
    if update.effective_chat and update.effective_chat.type == "private":
        await update.effective_message.reply_text(content)
        return

    user_id = update.effective_user.id
    bot_username = context.bot.username

    # 生成唯一 token
    token = secrets.token_urlsafe(16)
    db.save_pending_message(token=token, user_id=user_id, content=content)

    # 构建深链
    deep_link = f"https://t.me/{bot_username}?start=view_{token}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(button_text, url=deep_link)]
    ])

    await update.effective_message.reply_text(group_hint, reply_markup=keyboard)