"""入群验证（CAPTCHA）、欢迎/告别消息、黑名单检查"""
import asyncio
import logging
import secrets
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ContextTypes
from services import database as db
from utils.captcha import generate_image_captcha

logger = logging.getLogger(__name__)

# 禁言权限：只禁止发消息，其他权限全部保留（用户仍可查看群）
# 注意：ChatPermissions 默认值全是 False，必须显式设 True
# 发送类全部 False（真正禁言），管理类 True（保持能查看群）
MUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=True,
    can_change_info=True,
    can_invite_users=True,
    can_pin_messages=True,
    can_manage_topics=True,
)

# 正常权限：恢复全部
FULL_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_change_info=True,
    can_invite_users=True,
    can_pin_messages=True,
    can_manage_topics=True,
)


async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """新成员入群处理"""
    if not update.effective_chat or update.effective_chat.type == "private":
        return

    chat_id = update.effective_chat.id
    settings = db.get_settings(chat_id)

    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue

        inviter_id = update.message.from_user.id if update.message.from_user.id != member.id else 0
        db.track_invite(chat_id, member.id, inviter_id)

        if db.is_blacklisted(chat_id, member.id):
            try:
                await context.bot.ban_chat_member(chat_id, member.id)
                await update.effective_message.reply_text(
                    f"🚫 {member.first_name} 在黑名单中，已自动封禁"
                )
            except Exception:
                pass
            continue

        if settings["captcha_enabled"]:
            await _send_captcha(update, context, member, settings)
        elif settings["new_user_mute_minutes"] > 0:
            await _mute_new_user(update, context, member, settings)


async def on_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """成员离开处理"""
    if not update.effective_chat or update.effective_chat.type == "private":
        return

    chat_id = update.effective_chat.id
    settings = db.get_settings(chat_id)

    if not settings["goodbye_enabled"]:
        return

    left_member = update.message.left_chat_member
    if left_member.id == context.bot.id:
        return

    text = settings["goodbye_text"].format(
        user=left_member.first_name,
        chat=update.effective_chat.title or "本群",
    )
    await update.effective_message.reply_text(text)


async def handle_captcha_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理验证码按钮回调"""
    query = update.callback_query
    try:
        await query.answer("请在私聊中完成验证")
    except Exception:
        pass


async def handle_verify_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE, token: str):
    """处理 /start verify_TOKEN 深链"""
    captcha = db.get_captcha_by_token(token)
    if not captcha:
        await update.effective_message.reply_text("❌ 验证链接不存在或已过期")
        return

    settings = db.get_settings(captcha["chat_id"])
    timeout = settings.get("captcha_timeout", 120)
    if time.time() - captcha["created_at"] > timeout:
        db.delete_captcha(captcha["chat_id"], captcha["user_id"])
        await update.effective_message.reply_text("❌ 验证已超时，请重新入群")
        return

    if update.effective_user.id != captcha["user_id"]:
        await update.effective_message.reply_text("❌ 此验证链接不属于你")
        return

    image_bytes, answer = generate_image_captcha()
    db.update_captcha_answer(captcha["chat_id"], captcha["user_id"], answer)

    remaining = int(timeout - (time.time() - captcha["created_at"]))
    await update.effective_message.reply_photo(
        photo=image_bytes,
        caption=(
            "🔐 请输入图片中的验证码（不区分大小写）\n\n"
            f"⏰ 剩余时间：{remaining}秒\n"
            "💡 直接在此聊天中输入答案即可"
        ),
    )


async def handle_captcha_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理私聊中的验证码答案"""
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()

    captcha = db.get_captcha_by_user(user_id)
    if not captcha:
        return

    settings = db.get_settings(captcha["chat_id"])
    timeout = settings.get("captcha_timeout", 120)
    if time.time() - captcha["created_at"] > timeout:
        db.delete_captcha(captcha["chat_id"], captcha["user_id"])
        await update.effective_message.reply_text("❌ 验证已超时，请重新入群")
        return

    if text.upper() == captcha["answer"].upper():
        db.delete_captcha(captcha["chat_id"], captcha["user_id"])
        db.remove_mute(captcha["chat_id"], captcha["user_id"])

        try:
            await context.bot.restrict_chat_member(
                captcha["chat_id"], captcha["user_id"],
                permissions=FULL_PERMISSIONS,
            )
        except Exception as e:
            logger.warning(f"解除禁言失败: {e}")

        await update.effective_message.reply_text("✅ 验证通过！你现在可以在群中发言了")

        try:
            await context.bot.delete_message(
                chat_id=captcha["chat_id"],
                message_id=captcha["message_id"],
            )
        except Exception:
            pass

        try:
            if settings["welcome_enabled"]:
                chat = await context.bot.get_chat(captcha["chat_id"])
                welcome_text = settings["welcome_text"].format(
                    user=update.effective_user.first_name,
                    chat=chat.title or "本群",
                )
                await context.bot.send_message(captcha["chat_id"], welcome_text)
        except Exception:
            pass
    else:
        image_bytes, answer = generate_image_captcha()
        db.update_captcha_answer(captcha["chat_id"], captcha["user_id"], answer)
        await update.effective_message.reply_photo(
            photo=image_bytes,
            caption="❌ 答案错误，请重新输入：",
        )


async def _send_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE, member, settings):
    """发送验证码（深链模式）"""
    chat_id = update.effective_chat.id
    token = secrets.token_urlsafe(16)
    answer = "pending"

    bot_username = context.bot.username
    deep_link = f"https://t.me/{bot_username}?start=verify_{token}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 点击进行人机验证", url=deep_link)]
    ])

    timeout = settings["captcha_timeout"]
    msg = await update.effective_chat.send_message(
        f"🔐 {member.first_name} 请在 {timeout}秒 内完成验证：\n\n"
        "👇 点击下方按钮进入私聊完成验证",
        reply_markup=keyboard,
    )

    db.save_captcha_with_token(chat_id, member.id, msg.message_id, answer, token)

    until = time.time() + timeout
    try:
        await context.bot.restrict_chat_member(
            chat_id, member.id,
            permissions=MUTE_PERMISSIONS,
            until_date=int(until),
        )
        db.add_mute(chat_id, member.id, until)
    except Exception:
        pass

    asyncio.create_task(
        _schedule_captcha_timeout(context, chat_id, member.id, msg.message_id, timeout)
    )


async def _schedule_captcha_timeout(context: ContextTypes.DEFAULT_TYPE, chat_id, user_id, message_id, timeout):
    """验证超时后踢出"""
    await asyncio.sleep(timeout)

    captcha = db.get_captcha(chat_id, user_id)
    if captcha:
        db.delete_captcha(chat_id, user_id)
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=message_id,
            )
        except Exception:
            pass

        try:
            await context.bot.ban_chat_member(chat_id, user_id)
            await context.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        except Exception:
            pass


async def _mute_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE, member, settings):
    """新用户静默期"""
    chat_id = update.effective_chat.id
    minutes = settings["new_user_mute_minutes"]
    until = time.time() + minutes * 60

    try:
        await context.bot.restrict_chat_member(
            chat_id, member.id,
            permissions=MUTE_PERMISSIONS,
            until_date=int(until),
        )
        db.add_mute(chat_id, member.id, until)
        await update.effective_message.reply_text(
            f"🔇 {member.first_name} 新用户静默期 {minutes} 分钟"
        )
    except Exception:
        pass