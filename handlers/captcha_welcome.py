"""入群验证（CAPTCHA）、欢迎/告别消息、黑名单检查"""
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ContextTypes
from services import database as db
from utils.captcha import generate_math_captcha


async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """新成员入群处理"""
    if not update.effective_chat or update.effective_chat.type == "private":
        return

    chat_id = update.effective_chat.id
    settings = db.get_settings(chat_id)

    for member in update.message.new_chat_members:
        # 跳过 bot 自己
        if member.id == context.bot.id:
            continue

        # 记录邀请追踪
        inviter_id = update.message.from_user.id if update.message.from_user.id != member.id else 0
        db.track_invite(chat_id, member.id, inviter_id)

        # 黑名单检查
        if db.is_blacklisted(chat_id, member.id):
            try:
                await context.bot.ban_chat_member(chat_id, member.id)
                await update.effective_message.reply_text(
                    f"🚫 {member.first_name} 在黑名单中，已自动封禁"
                )
            except Exception:
                pass
            continue

        # 验证码
        if settings["captcha_enabled"]:
            await _send_captcha(update, context, member, settings)
        elif settings["new_user_mute_minutes"] > 0:
            # 没有验证码但开启了静默期
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

    if not query.message or not query.from_user:
        await query.answer("❌ 无法处理", show_alert=True)
        return

    chat_id = query.message.chat.id
    user_id = query.from_user.id

    captcha = db.get_captcha(chat_id, user_id)
    if not captcha:
        await query.answer("❌ 验证码不存在或已过期", show_alert=True)
        return

    # 检查答案
    callback_data = query.data
    if callback_data == f"captcha_{captcha['answer']}_{user_id}":
        # 验证成功
        await query.answer("✅ 验证通过！")
        db.delete_captcha(chat_id, user_id)
        db.remove_mute(chat_id, user_id)
        try:
            await context.bot.restrict_chat_member(
                chat_id, user_id,
                permissions=ChatPermissions(
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
                ),
            )
        except Exception:
            pass
        await query.edit_message_text(f"✅ {query.from_user.first_name} 验证通过，欢迎加入！")

        # 发送欢迎消息
        settings = db.get_settings(chat_id)
        if settings["welcome_enabled"]:
            text = settings["welcome_text"].format(
                user=query.from_user.first_name,
                chat=query.message.chat.title or "本群",
            )
            await query.message.chat.send_message(text)
    else:
        await query.answer("❌ 答案错误，请重试", show_alert=True)


async def _send_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE, member, settings):
    """发送验证码"""
    chat_id = update.effective_chat.id
    question, answer = generate_math_captcha()

    # 生成错误答案作为干扰项
    import random
    wrong_answers = set()
    correct = int(answer)
    while len(wrong_answers) < 3:
        wrong = correct + random.choice([-3, -2, -1, 1, 2, 3, 4, 5])
        if wrong != correct and wrong >= 0:
            wrong_answers.add(str(wrong))

    all_answers = [answer] + list(wrong_answers)
    random.shuffle(all_answers)

    keyboard = []
    row = []
    for a in all_answers:
        row.append(InlineKeyboardButton(str(a), callback_data=f"captcha_{a}_{member.id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.effective_chat.send_message(
        f"🔐 {member.first_name} 请在 {settings['captcha_timeout']}秒 内完成验证：\n\n"
        f"{question}",
        reply_markup=reply_markup,
    )

    # 保存验证码
    db.save_captcha(chat_id, member.id, msg.message_id, answer)

    # 禁言用户直到验证通过（完全禁言，不允许任何操作）
    timeout = settings["captcha_timeout"]
    until = __import__('time').time() + timeout
    try:
        await context.bot.restrict_chat_member(
            chat_id, member.id,
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
        db.add_mute(chat_id, member.id, until)
    except Exception:
        pass

    # 设置超时自动踢出
    await _schedule_captcha_timeout(context, chat_id, member.id, msg.message_id, timeout)


async def _schedule_captcha_timeout(context: ContextTypes.DEFAULT_TYPE, chat_id, user_id, message_id, timeout):
    """验证超时后踢出"""
    await asyncio.sleep(timeout)

    captcha = db.get_captcha(chat_id, user_id)
    if captcha:
        db.delete_captcha(chat_id, user_id)
        try:
            await context.bot.ban_chat_member(chat_id, user_id)
            await context.bot.unban_chat_member(chat_id, user_id)
            await context.bot.edit_message_text(
                "⏰ 验证超时，已自动踢出",
                chat_id=chat_id,
                message_id=message_id,
            )
        except Exception:
            pass


async def _mute_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE, member, settings):
    """新用户静默期"""
    import time
    chat_id = update.effective_chat.id
    minutes = settings["new_user_mute_minutes"]
    until = time.time() + minutes * 60

    try:
        await context.bot.restrict_chat_member(
            chat_id, member.id,
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
        db.add_mute(chat_id, member.id, until)
        await update.effective_message.reply_text(
            f"🔇 {member.first_name} 新用户静默期 {minutes} 分钟"
        )
    except Exception:
        pass
