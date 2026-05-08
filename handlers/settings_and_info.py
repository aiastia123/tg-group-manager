"""群组配置、群规、用户信息、备注、黑名单、日志、敏感词、举报"""
import time
from telegram import Update
from telegram.ext import ContextTypes
from utils.decorators import admin_required
from services import database as db


# ─── 群规 ───

@admin_required
async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置群规：/setrules <内容>"""
    if not context.args:
        await update.effective_message.reply_text("用法：/setrules <群规内容>")
        return
    text = " ".join(context.args)
    db.set_setting(update.effective_chat.id, "rules_text", text)
    db.add_log(update.effective_chat.id, update.effective_user.id, "set_rules", details="更新群规")
    await update.effective_message.reply_text("✅ 群规已更新")


async def show_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看群规：/rules"""
    rules = db.get_setting(update.effective_chat.id, "rules_text")
    await update.effective_message.reply_text(f"📜 群规：\n\n{rules}")


# ─── 配置 ───

@admin_required
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看当前配置：/settings"""
    chat_id = update.effective_chat.id
    settings = db.get_settings(chat_id)

    msg = "⚙️ 当前群组配置：\n\n"
    labels = {
        "warn_limit": "警告上限",
        "new_user_mute_minutes": "新用户静默(分)",
        "flood_messages": "洪水消息数",
        "flood_seconds": "洪水时间窗(秒)",
        "link_filter": "链接过滤",
        "media_filter": "媒体过滤",
        "welcome_enabled": "欢迎消息",
        "goodbye_enabled": "告别消息",
        "captcha_enabled": "入群验证",
        "captcha_timeout": "验证超时(秒)",
        "auto_delete_seconds": "自动删除(秒)",
        "forward_filter": "转发过滤",
    }
    for key, label in labels.items():
        val = settings.get(key, "")
        msg += f"  {label}：{val}\n"

    msg += "\n修改：/setconfig <配置项> <值>\n例：/setconfig warn_limit 5"

    await update.effective_message.reply_text(msg)


@admin_required
async def set_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """修改配置：/setconfig <key> <value>"""
    if len(context.args) < 2:
        await update.effective_message.reply_text("用法：/setconfig <配置项> <值>")
        return

    key = context.args[0]
    value = " ".join(context.args[1:])
    defaults = db.DEFAULTS

    if key not in defaults:
        valid = ", ".join(defaults.keys())
        await update.effective_message.reply_text(f"❌ 无效的配置项\n可用项：{valid}")
        return

    # 类型转换
    default_val = defaults[key]
    if isinstance(default_val, bool):
        value = value.lower() in ("true", "1", "yes", "开", "开启")
    elif isinstance(default_val, int):
        try:
            value = int(value)
        except ValueError:
            await update.effective_message.reply_text("❌ 值必须是数字")
            return

    db.set_setting(update.effective_chat.id, key, value)
    db.add_log(update.effective_chat.id, update.effective_user.id, "set_config",
               details=f"设置 {key} = {value}")
    await update.effective_message.reply_text(f"✅ 已设置 {key} = {value}")


# ─── 用户信息 ───

@admin_required
async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看用户信息：/info @user"""
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
        await update.effective_message.reply_text("用法：/info <用户ID或回复消息>")
        return

    chat_id = update.effective_chat.id
    display = target.username or target.first_name
    warns = db.get_warns(chat_id, target.id)
    note = db.get_user_note(chat_id, target.id)
    blacklisted = db.is_blacklisted(chat_id, target.id)
    muted = db.is_muted(chat_id, target.id)
    invite = db.get_invite_tracking(chat_id, target.id)

    msg = f"👤 用户信息：{display}\n"
    msg += f"  ID：{target.id}\n"
    msg += f"  警告：{len(warns)} 次\n"
    msg += f"  黑名单：{'是' if blacklisted else '否'}\n"
    msg += f"  禁言中：{'是' if muted else '否'}\n"
    if note:
        msg += f"  备注：{note['note']}\n"
        if note['tags']:
            msg += f"  标签：{note['tags']}\n"
    if invite:
        msg += f"  邀请人ID：{invite.get('inviter_id', '未知')}\n"

    await update.effective_message.reply_text(msg)


# ─── 备注 ───

@admin_required
async def set_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置备注：/note @user <备注内容>"""
    target = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        note_text = " ".join(context.args) if context.args else ""
    elif len(context.args) >= 2:
        try:
            uid = int(context.args[0])
            member = await context.bot.get_chat_member(update.effective_chat.id, uid)
            target = member.user if hasattr(member, 'user') else member
            note_text = " ".join(context.args[1:])
        except (ValueError, Exception):
            await update.effective_message.reply_text("❌ 找不到用户")
            return
    else:
        await update.effective_message.reply_text("用法：/note <用户ID或回复> <备注>")
        return

    if not target or not note_text:
        await update.effective_message.reply_text("❌ 请提供备注内容")
        return

    db.set_user_note(update.effective_chat.id, target.id, note=note_text)
    display = target.username or target.first_name
    await update.effective_message.reply_text(f"✅ 已为 {display} 添加备注：{note_text}")


@admin_required
async def set_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置标签：/tags @user <标签1,标签2>"""
    target = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        tags_text = " ".join(context.args) if context.args else ""
    elif len(context.args) >= 2:
        try:
            uid = int(context.args[0])
            member = await context.bot.get_chat_member(update.effective_chat.id, uid)
            target = member.user if hasattr(member, 'user') else member
            tags_text = " ".join(context.args[1:])
        except (ValueError, Exception):
            await update.effective_message.reply_text("❌ 找不到用户")
            return
    else:
        await update.effective_message.reply_text("用法：/tags <用户ID或回复> <标签1,标签2>")
        return

    if not target:
        return

    db.set_user_note(update.effective_chat.id, target.id, tags=tags_text)
    display = target.username or target.first_name
    await update.effective_message.reply_text(f"✅ 已为 {display} 设置标签：{tags_text}")


# ─── 黑名单 ───

@admin_required
async def add_to_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """添加黑名单：/blacklist @user [原因]"""
    target = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        reason = " ".join(context.args) if context.args else ""
    elif context.args:
        try:
            uid = int(context.args[0])
            member = await context.bot.get_chat_member(update.effective_chat.id, uid)
            target = member.user if hasattr(member, 'user') else member
            reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""
        except (ValueError, Exception):
            await update.effective_message.reply_text("❌ 找不到用户")
            return
    else:
        await update.effective_message.reply_text("用法：/blacklist <用户ID或回复> [原因]")
        return

    if not target:
        return

    chat_id = update.effective_chat.id
    db.add_blacklist(chat_id, target.id, reason, update.effective_user.id)
    display = target.username or target.first_name
    db.add_log(chat_id, update.effective_user.id, "blacklist", target.id,
               f"添加 {display} 到黑名单" + (f"，原因：{reason}" if reason else ""))

    # 尝试踢出
    try:
        await context.bot.ban_chat_member(chat_id, target.id)
    except Exception:
        pass

    await update.effective_message.reply_text(f"✅ 已将 {display} 加入黑名单")


@admin_required
async def remove_from_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """移除黑名单：/unblacklist @user"""
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
        await update.effective_message.reply_text("用法：/unblacklist <用户ID或回复>")
        return

    chat_id = update.effective_chat.id
    if db.remove_blacklist(chat_id, target.id):
        display = target.username or target.first_name
        try:
            await context.bot.unban_chat_member(chat_id, target.id)
        except Exception:
            pass
        db.add_log(chat_id, update.effective_user.id, "unblacklist", target.id,
                   f"将 {display} 移出黑名单")
        await update.effective_message.reply_text(f"✅ 已将 {display} 移出黑名单")
    else:
        await update.effective_message.reply_text("❌ 该用户不在黑名单中")


@admin_required
async def show_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看黑名单：/blacklists"""
    chat_id = update.effective_chat.id
    bl = db.get_blacklist(chat_id)

    if not bl:
        await update.effective_message.reply_text("📭 黑名单为空")
        return

    msg = "📋 黑名单：\n\n"
    for i, entry in enumerate(bl[:20], 1):
        try:
            member = await context.bot.get_chat_member(chat_id, entry["user_id"])
            name = member.user.username or member.user.first_name
        except Exception:
            name = str(entry["user_id"])
        reason = entry["reason"] or "无原因"
        msg += f"  {i}. {name} — {reason}\n"

    await update.effective_message.reply_text(msg)


# ─── 操作日志 ───

@admin_required
async def show_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看日志：/logs [数量]"""
    limit = 20
    if context.args:
        try:
            limit = min(int(context.args[0]), 50)
        except ValueError:
            pass

    logs = db.get_logs(update.effective_chat.id, limit)
    if not logs:
        await update.effective_message.reply_text("📭 没有操作日志")
        return

    msg = "📋 操作日志：\n\n"
    for log in logs:
        ts = time.strftime("%m-%d %H:%M", time.localtime(log["created_at"]))
        msg += f"  [{ts}] {log['action']}"
        if log["details"]:
            msg += f" — {log['details']}"
        msg += "\n"

    await update.effective_message.reply_text(msg)


# ─── 敏感词 ───

@admin_required
async def add_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """添加敏感词：/addword <词语>"""
    if not context.args:
        await update.effective_message.reply_text("用法：/addword <词语>")
        return

    word = context.args[0]
    db.add_sensitive_word(update.effective_chat.id, word, update.effective_user.id)
    await update.effective_message.reply_text(f"✅ 已添加敏感词：{word}")


@admin_required
async def remove_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """移除敏感词：/delword <词语>"""
    if not context.args:
        await update.effective_message.reply_text("用法：/delword <词语>")
        return

    word = context.args[0]
    if db.remove_sensitive_word(update.effective_chat.id, word):
        await update.effective_message.reply_text(f"✅ 已移除敏感词：{word}")
    else:
        await update.effective_message.reply_text("❌ 该词不在敏感词列表中")


@admin_required
async def list_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看敏感词：/words"""
    words = db.get_sensitive_words(update.effective_chat.id)
    if not words:
        await update.effective_message.reply_text("📭 敏感词列表为空")
        return
    await update.effective_message.reply_text(f"📋 敏感词列表：\n{', '.join(words)}")


# ─── 举报 ───

async def report_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """举报用户：回复消息使用 /report [原因]"""
    if not update.message.reply_to_message:
        await update.effective_message.reply_text("用法：回复目标消息使用 /report [原因]")
        return

    target = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "未提供原因"
    chat_id = update.effective_chat.id

    report_id = db.add_report(
        chat_id,
        update.effective_user.id,
        target.id,
        reason,
        update.message.reply_to_message.message_id,
    )

    display = target.username or target.first_name
    await update.effective_message.reply_text(
        f"✅ 已举报 {display}\n原因：{reason}\n等待管理员处理（举报ID：{report_id}）"
    )


@admin_required
async def show_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看举报：/reports"""
    status = context.args[0] if context.args else "pending"
    reports = db.get_reports(update.effective_chat.id, status)

    if not reports:
        await update.effective_message.reply_text("📭 没有待处理的举报")
        return

    msg = "📋 举报列表：\n\n"
    for r in reports:
        ts = time.strftime("%m-%d %H:%M", time.localtime(r["created_at"]))
        msg += (
            f"  #{r['id']} [{ts}]\n"
            f"  举报人ID：{r['reporter_id']} → 目标ID：{r['target_id']}\n"
            f"  原因：{r['reason']}\n\n"
        )

    msg += "处理：/resolve <举报ID> [done/dismiss]"
    await update.effective_message.reply_text(msg)


@admin_required
async def resolve_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理举报：/resolve <ID> [done/dismiss]"""
    if len(context.args) < 1:
        await update.effective_message.reply_text("用法：/resolve <举报ID> [done/dismiss]")
        return

    try:
        report_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ ID必须是数字")
        return

    status = context.args[1] if len(context.args) > 1 else "done"
    if status not in ("done", "dismiss"):
        status = "done"

    db.update_report_status(report_id, status)
    db.add_log(update.effective_chat.id, update.effective_user.id, "resolve_report",
               details=f"处理举报 #{report_id} → {status}")
    await update.effective_message.reply_text(f"✅ 举报 #{report_id} 已标记为 {status}")
