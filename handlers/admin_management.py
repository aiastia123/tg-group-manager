"""管理员设置 & 权限管理"""
from telegram import Update
from telegram.ext import ContextTypes
from utils.decorators import admin_required, require_perm, PERM_LABELS
from services import database as db
from services.database import ALL_PERMISSIONS


@require_perm("admin")
async def set_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置管理员：/setadmin @user [权限1 权限2 ...]
    不指定权限则默认全部权限
    例：/setadmin @user kick ban warn
    """
    target = await _get_target(update, context)
    if not target:
        return

    chat_id = update.effective_chat.id
    display = target.username or target.first_name

    # 解析权限参数（跳过第一个参数，那可能是 user_id）
    # 从 context.args 中提取权限（第一个元素如果是数字就是 user_id，跳过）
    perm_args = list(context.args) if context.args else []
    if perm_args:
        try:
            int(perm_args[0])
            perm_args = perm_args[1:]  # 跳过 user_id
        except ValueError:
            pass

    # 过滤出有效权限
    valid_perms = set()
    for p in perm_args:
        p = p.lower().strip(",")
        if p in ALL_PERMISSIONS:
            valid_perms.add(p)

    # 没指定权限或指定了 "all" → 全部权限
    if not valid_perms or "all" in [p.lower() for p in perm_args]:
        valid_perms = set(ALL_PERMISSIONS)

    # 只设置 Bot 命令权限，不改变 TG 管理员身份
    db.add_custom_admin(chat_id, target.id, update.effective_user.id, permissions=valid_perms)
    db.add_log(chat_id, update.effective_user.id, "set_admin", target.id,
               f"设置 {display} 为 Bot 管理员，权限：{','.join(valid_perms)}")

    perm_list = _format_perms(valid_perms)
    await update.effective_message.reply_text(
        f"✅ {display} 已设为 Bot 管理员\n"
        f"Bot 权限：{perm_list}"
    )


@require_perm("admin")
async def add_perm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """追加权限：/addperm @user <权限1> [权限2] ..."""
    target = await _get_target(update, context)
    if not target:
        return

    if len(context.args) < 2:
        await update.effective_message.reply_text(
            f"用法：/addperm <用户ID或回复> <权限...>\n"
            f"可用权限：{', '.join(ALL_PERMISSIONS)}"
        )
        return

    chat_id = update.effective_chat.id
    display = target.username or target.first_name

    # 解析要添加的权限
    perm_args = context.args[1:] if context.args else []
    new_perms = set()
    invalid = []
    for p in perm_args:
        p = p.lower().strip(",")
        if p in ALL_PERMISSIONS:
            new_perms.add(p)
        else:
            invalid.append(p)

    if not new_perms:
        await update.effective_message.reply_text(f"❌ 没有有效权限\n可用：{', '.join(ALL_PERMISSIONS)}")
        return

    # 获取当前权限并合并
    current = db.get_admin_permissions(chat_id, target.id)
    merged = current | new_perms
    db.set_admin_permissions(chat_id, target.id, merged)

    db.add_log(chat_id, update.effective_user.id, "add_perm", target.id,
               f"追加 {display} 权限：{','.join(new_perms)}")

    msg = f"✅ 已为 {display} 追加权限：{_format_perms(new_perms)}"
    if invalid:
        msg += f"\n⚠️ 无效项已忽略：{', '.join(invalid)}"
    msg += f"\n当前全部权限：{_format_perms(merged)}"
    await update.effective_message.reply_text(msg)


@require_perm("admin")
async def del_perm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """移除权限：/delperm @user <权限1> [权限2] ..."""
    target = await _get_target(update, context)
    if not target:
        return

    if len(context.args) < 2:
        await update.effective_message.reply_text(
            f"用法：/delperm <用户ID或回复> <权限...>\n"
            f"可用权限：{', '.join(ALL_PERMISSIONS)}"
        )
        return

    chat_id = update.effective_chat.id
    display = target.username or target.first_name

    perm_args = context.args[1:] if context.args else []
    remove_perms = set()
    for p in perm_args:
        p = p.lower().strip(",")
        if p in ALL_PERMISSIONS:
            remove_perms.add(p)

    if not remove_perms:
        await update.effective_message.reply_text("❌ 没有有效权限")
        return

    current = db.get_admin_permissions(chat_id, target.id)
    remaining = current - remove_perms

    if not remaining:
        # 没有任何权限了 → 直接移除管理员
        db.remove_custom_admin(chat_id, target.id)
        db.add_log(chat_id, update.effective_user.id, "remove_admin", target.id,
                   f"移除 {display} 全部权限，自动撤销管理员")
        await update.effective_message.reply_text(f"✅ 已移除 {display} 的全部权限，自动撤销管理员身份")
        return

    db.set_admin_permissions(chat_id, target.id, remaining)
    db.add_log(chat_id, update.effective_user.id, "del_perm", target.id,
               f"移除 {display} 权限：{','.join(remove_perms)}")

    await update.effective_message.reply_text(
        f"✅ 已移除 {display} 的权限：{_format_perms(remove_perms)}\n"
        f"当前剩余权限：{_format_perms(remaining)}"
    )


@require_perm("admin")
async def show_perms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看权限：/perms @user"""
    target = await _get_target(update, context)
    if not target:
        return

    chat_id = update.effective_chat.id
    display = target.username or target.first_name

    # 检查是否是 TG 原生管理员
    member = await update.effective_chat.get_member(target.id)
    if member.status in ("administrator", "creator"):
        role = "群主" if member.status == "creator" else "TG管理员"
        await update.effective_message.reply_text(
            f"👤 {display} 是 {role}，拥有全部权限"
        )
        return

    if not db.is_custom_admin(chat_id, target.id):
        await update.effective_message.reply_text(f"❌ {display} 不是管理员")
        return

    perms = db.get_admin_permissions(chat_id, target.id)
    if perms == set(ALL_PERMISSIONS):
        await update.effective_message.reply_text(f"👤 {display} 的权限：全部")
    else:
        msg = f"👤 {display} 的权限：\n"
        for p in ALL_PERMISSIONS:
            mark = "✅" if p in perms else "❌"
            label = PERM_LABELS.get(p, p)
            msg += f"  {mark} {label}（{p}）\n"
        await update.effective_message.reply_text(msg)


@require_perm("admin")
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消管理员：/removeadmin @user
    同时撤销 Bot 管理员权限和 TG 管理员身份
    """
    target = await _get_target(update, context)
    if not target:
        return

    chat_id = update.effective_chat.id
    display = target.username or target.first_name

    # 检查目标身份
    target_member = await update.effective_chat.get_member(target.id)
    is_tg_admin = target_member.status == "administrator"
    is_creator = target_member.status == "creator"
    was_custom = db.is_custom_admin(chat_id, target.id)

    if is_creator:
        await update.effective_message.reply_text("❌ 无法移除群主")
        return

    if not is_tg_admin and not was_custom:
        await update.effective_message.reply_text(f"❌ {display} 不是管理员")
        return

    msg = ""

    # 撤销 TG 管理员身份
    if is_tg_admin:
        try:
            await context.bot.promote_chat_member(
                chat_id, target.id,
                is_anonymous=False,
                can_manage_chat=False,
                can_delete_messages=False,
                can_manage_video_chats=False,
                can_restrict_members=False,
                can_promote_members=False,
                can_change_info=False,
                can_invite_users=False,
                can_post_messages=False,
                can_edit_messages=False,
                can_pin_messages=False,
                can_manage_topics=False,
            )
            msg += "✅ TG 管理员身份已撤销\n"
        except Exception as e:
            msg += f"⚠️ TG 管理员身份撤销失败：{e}\n"

    # 移除 Bot 管理员权限
    if was_custom:
        db.remove_custom_admin(chat_id, target.id)
        msg += "✅ Bot 管理员权限已移除\n"

    db.add_log(chat_id, update.effective_user.id, "remove_admin", target.id,
               f"取消 {display} 的管理员")
    await update.effective_message.reply_text(msg.strip())


@admin_required
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看管理员列表：/admins"""
    chat_id = update.effective_chat.id
    bot_id = context.bot.id
    custom = db.get_custom_admins(chat_id)

    administrators = await context.bot.get_chat_administrators(chat_id)

    # 收集 TG 管理员 ID（用于去重）
    tg_admin_ids = set()
    msg = "📋 管理员列表：\n\n"
    msg += "🔹 TG 管理员：\n"
    for admin in administrators:
        # 跳过 bot 自身
        if admin.user.id == bot_id:
            continue
        tg_admin_ids.add(admin.user.id)
        name = admin.user.username or admin.user.first_name or f"用户{admin.user.id}"
        role = "群主" if admin.status == "creator" else "管理员"
        msg += f"  • {name}（{role}，全部权限）\n"

    # Bot 管理员：排除已是 TG 管理员的，避免重复
    bot_only_admins = [a for a in custom if a["user_id"] not in tg_admin_ids]
    if bot_only_admins:
        msg += "\n🔹 Bot 管理员：\n"
        for a in bot_only_admins:
            try:
                member = await context.bot.get_chat_member(chat_id, a["user_id"])
                name = member.user.username or member.user.first_name or f"用户{a['user_id']}"
            except Exception:
                name = f"用户{a['user_id']}"
            perms = db.get_admin_permissions(chat_id, a["user_id"])
            if perms == set(ALL_PERMISSIONS):
                perm_text = "全部权限"
            else:
                perm_text = ", ".join(PERM_LABELS.get(p, p) for p in sorted(perms))
            msg += f"  • {name}（{perm_text}）\n"

    await update.effective_message.reply_text(msg)


# ─── 辅助函数 ───

def _format_perms(perms: set) -> str:
    """格式化权限列表"""
    if not perms:
        return "无"
    if perms == set(ALL_PERMISSIONS):
        return "全部"
    return ", ".join(PERM_LABELS.get(p, p) for p in sorted(perms))


async def _get_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    if context.args:
        try:
            uid = int(context.args[0])
            member = await context.bot.get_chat_member(update.effective_chat.id, uid)
            return member.user if hasattr(member, 'user') else member
        except (ValueError, Exception):
            pass
    await update.effective_message.reply_text("❌ 请回复目标用户的消息，或提供用户 ID")
    return None
