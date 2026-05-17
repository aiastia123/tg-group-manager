"""消息过滤器：敏感词、链接、媒体、转发、洪水检测"""
import re
from telegram import Update, MessageEntity
from telegram.ext import ContextTypes
from utils.decorators import is_user_admin
from services import database as db


async def filter_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """消息过滤器（核心）"""
    if not update.effective_chat or update.effective_chat.type == "private":
        return
    if not update.effective_user:
        return
    if not update.effective_message:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # 跳过管理员
    if await is_user_admin(update, context, user_id):
        return

    # 跳过 bot
    if update.effective_user.is_bot:
        return

    settings = db.get_settings(chat_id)
    text = update.effective_message.text or update.effective_message.caption or ""

    # ── 敏感词检查 ──
    found_word = db.contains_sensitive_word(chat_id, text)
    if found_word:
        try:
            await update.effective_message.delete()
        except Exception:
            pass

        # 自动添加警告（与 /warn 一致）
        warn_limit = db.get_settings(chat_id)["warn_limit"]
        reason = f"触发敏感词：{found_word}"
        count = db.add_warn(chat_id, user_id, reason, 0)  # admin_id=0 表示系统自动
        display = update.effective_user.username or update.effective_user.first_name

        db.add_log(chat_id, 0, "filter_word", user_id,
                   f"敏感词过滤：{found_word}，自动警告 ({count}/{warn_limit})")

        if count >= warn_limit:
            # 警告满自动踢出
            try:
                await context.bot.ban_chat_member(chat_id, user_id)
                await context.bot.unban_chat_member(chat_id, user_id)
                db.clear_warns(chat_id, user_id)
                db.add_log(chat_id, 0, "auto_kick", user_id,
                           f"敏感词警告满 {warn_limit} 次自动踢出 {display}")
                await update.effective_chat.send_message(
                    f"⚠️ {display} 触发敏感词「{found_word}」\n"
                    f"已达 {warn_limit} 次警告上限，已自动踢出"
                )
            except Exception:
                await update.effective_chat.send_message(
                    f"⚠️ {display} 触发敏感词「{found_word}」({count}/{warn_limit})\n"
                    f"❌ 自动踢出失败"
                )
        else:
            await update.effective_chat.send_message(
                f"⚠️ {display} 触发敏感词「{found_word}」\n"
                f"收到警告 ({count}/{warn_limit})"
            )
        return

    # ── 链接过滤 ──
    if settings["link_filter"]:
        has_link = bool(update.effective_message.entities and any(
            e.type in (MessageEntity.URL, MessageEntity.TEXT_LINK)
            for e in update.effective_message.entities
        ))
        # 也检查 caption 中的链接
        if not has_link and update.effective_message.caption_entities:
            has_link = any(
                e.type in (MessageEntity.URL, MessageEntity.TEXT_LINK)
                for e in update.effective_message.caption_entities
            )
        # 简单 URL 正则
        if not has_link and re.search(r'https?://\S+', text):
            has_link = True

        if has_link:
            try:
                await update.effective_message.delete()
                await update.effective_chat.send_message(
                    f"⚠️ {update.effective_user.first_name} 链接已被过滤"
                )
            except Exception:
                pass
            db.add_log(chat_id, 0, "filter_link", user_id, "链接过滤")
            return

    # ── 媒体过滤 ──
    if settings["media_filter"]:
        if (update.effective_message.photo or update.effective_message.video or
                update.effective_message.sticker or update.effective_message.animation or
                update.effective_message.document or update.effective_message.voice or
                update.effective_message.video_note):
            try:
                await update.effective_message.delete()
                await update.effective_chat.send_message(
                    f"⚠️ {update.effective_user.first_name} 媒体消息已被过滤"
                )
            except Exception:
                pass
            db.add_log(chat_id, 0, "filter_media", user_id, "媒体过滤")
            return

    # ── 转发过滤 ──
    if settings["forward_filter"]:
        if update.effective_message.forward_date:
            try:
                await update.effective_message.delete()
                await update.effective_chat.send_message(
                    f"⚠️ {update.effective_user.first_name} 转发消息已被过滤"
                )
            except Exception:
                pass
            db.add_log(chat_id, 0, "filter_forward", user_id, "转发过滤")
            return

    # ── 洪水检测 ──
    flood_msgs = settings["flood_messages"]
    flood_secs = settings["flood_seconds"]
    if flood_msgs > 0 and flood_secs > 0:
        if db.check_flood(chat_id, user_id, flood_msgs, flood_secs):
            # 洪水触发 → 禁言
            mute_minutes = 5
            import time
            until = time.time() + mute_minutes * 60
            try:
                await context.bot.restrict_chat_member(
                    chat_id, user_id,
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_other_messages=False,
                    until_date=int(until),
                )
                db.add_mute(chat_id, user_id, until)
                await update.effective_chat.send_message(
                    f"🔇 {update.effective_user.first_name} 因刷屏被禁言 {mute_minutes} 分钟"
                )
            except Exception:
                pass
            db.reset_flood(chat_id, user_id)
            db.add_log(chat_id, 0, "flood_mute", user_id,
                       f"洪水检测触发，禁言 {mute_minutes} 分钟")

    # ── 自动删除 ──
    auto_del = settings["auto_delete_seconds"]
    if auto_del > 0:
        import asyncio
        await asyncio.sleep(auto_del)
        try:
            await update.effective_message.delete()
        except Exception:
            pass
