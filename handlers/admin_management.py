"""管理员设置 & 权限管理"""
from telegram import Update
from telegram.ext import ContextTypes
from utils.decorators import admin_required, require_perm, PERM_LABELS
from services import database as db
from services.database import ALL_PERMISSIONS

# TG 管理员权限映射
TG_PERM_MAP = {
    "manage": ("can_manage_chat", "管理群组"),
    "delete": ("can_delete_messages", "删除消息"),
    "restrict": ("can_restrict_members", "限制成员"),
    "invite": ("can_invite_users", "邀请用户"),
    "pin": ("can_pin_messages", "置顶消息"),
    "video": ("can_manage_video_chats", "管理视频聊天"),
    "promote": ("can_promote_members", "提升管理员"),
    "info": ("can_change_info", "修改群信息"),
    "topics": ("can_manage_topics", "管理话题"),
}
TG_ALL_PERMS = list(TG_PERM_MAP.keys())

_SETADMIN_HELP = """📖 /setadmin 用法：

/setadmin bot <用户ID或回复> <权限...>
  设置 Bot 命令权限（不影响 TG 群组管理员）

/setadmin tg <用户ID或回复> <权限...>
  设置 TG 群组管理员权限

/setadmin off <用户ID或回复>
  彻底移除管理员（同时撤销 TG 和 Bot 权限）

━━━ Bot 可用权限 ━━━
  all — 全部权限
  kick（踢出用户）
  ban（封禁/解封）
  mute（禁言/解禁）
  warn（警告）
  delete（删除消息）
  pin（置顶/取消置顶）
  invite（管理邀请链接）
  admin（管理其他管理员）
  config（修改群组配置）
  blacklist（黑名单管理）
  filter（敏感词管理）
  logs（查看操作日志）
  announce（发布群公告）
  note（用户备注/标签）

━━━ TG 可用权限 ━━━
  all — 全部权限
  manage（管理群组）
  delete（删除消息）
  restrict（限制成员）
  invite（邀请用户）
  pin（置顶消息）
  video（管理视频聊天）
  promote（提升管理员）
  info（修改群信息）
  topics（管理话题）

━━━ 示例 ━━━
  /setadmin bot 123456 all — 全部 Bot 权限
  /setadmin bot 123456 kick warn — 只有踢出和警告
  /setadmin tg 123456 all — 全部 TG 管理权限
  /setadmin tg 123456 delete pin — 只能删消息和置顶
  /setadmin off 123456 — 移除所有管理员身份"""


@require_perm("admin")
async def set_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置管理员：统一入口
    /setadmin bot <用户> [权限] — Bot 管理员
    /setadmin tg <用户> [权限] — TG 管理员
    /setadmin off <用户> — 移除管理员
    无参数或 help — 显示帮助
    """
    if not context.args or context.args[0].lower() in ("help", "帮助", "?"):
        await update.effective_message.reply_text(_SETADMIN_HELP)
        return

    mode = context.args[0].lower()
    remaining_args = context.args[1:]

    if mode == "bot":
        await _set_bot_admin(update, context, remaining_args)
    elif mode == "tg":
        await _set_tg_admin(update, context, remaining_args)
    elif mode == "off":
        await _remove_admin(update, context, remaining_args)
    else:
        await update.effective_message.reply_text(_SETADMIN_HELP)


async def _set_bot_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list):
    """设置 Bot 管理员权限"""
    target = await _get_target_from_args(update, context, args)
    if not target:
        return

    # 回复消息时 args 全是权限，非回复时第一个是 user_id 要跳过
    perm_args = args if update.message.reply_to_message else (args[1:] if args else [])
    if not perm_args:
        await update.effective_message.reply_text(
            "❌ 请指定 Bot 权限\n\n"
            "用法：/setadmin bot <用户ID或回复> <权限...>\n"
            "输入 all 获取全部权限，或指定具体权限\n"
            "可用权限：all, kick, ban, mute, warn, delete, pin, invite, admin, config, blacklist, filter, logs, announce, note\n\n"
            "示例：\n"
            "  /setadmin bot 123456 all — 全部权限\n"
            "  /setadmin bot 123456 kick warn — 只有踢出和警告"
        )
        return

    chat_id = update.effective_chat.id
    display = target.username or target.first_name

    # 传入已计算好的 perm_args
    valid_perms = _parse_bot_perms(perm_args)

    db.add_custom_admin(chat_id, target.id, update.effective_user.id, permissions=valid_perms)
    db.add_log(chat_id, update.effective_user.id, "set_admin", target.id,
               f"设置 {display} 为 Bot 管理员，权限：{','.join(valid_perms)}")

    perm_list = _format_perms(valid_perms)
    await update.effective_message.reply_text(
        f"✅ {display} 已设为 Bot 管理员\n"
        f"Bot 权限：{perm_list}"
    )


async def _set_tg_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list):
    """设置 TG 管理员权限"""
    target = await _get_target_from_args(update, context, args)
    if not target:
        return

    chat_id = update.effective_chat.id
    display = target.username or target.first_name

    # 检查身份
    target_member = await update.effective_chat.get_member(target.id)
    if target_member.status == "creator":
        await update.effective_message.reply_text("❌ 该用户是群主，无需设置")
        return

    # 回复消息时 args 全是权限，非回复时第一个是 user_id 要跳过
    perm_args = args if update.message.reply_to_message else (args[1:] if args else [])
    if not perm_args:
        await update.effective_message.reply_text(
            "❌ 请指定 TG 权限\n\n"
            "用法：/setadmin tg <用户ID或回复> <权限...>\n"
            "输入 all 获取全部权限，或指定具体权限\n"
            "可用权限：all, manage, delete, restrict, invite, pin, video, promote, info, topics\n\n"
            "示例：\n"
            "  /setadmin tg 123456 all — 全部权限\n"
            "  /setadmin tg 123456 delete pin — 只能删消息和置顶"
        )
        return

    # 解析 TG 权限
    valid_tg = set()
    for p in perm_args:
        p = p.lower().strip(",")
        if p in TG_PERM_MAP:
            valid_tg.add(p)

    # 指定 all → 全部权限
    if "all" in [p.lower() for p in perm_args]:
        valid_tg = set(TG_ALL_PERMS)

    if not valid_tg:
        await update.effective_message.reply_text(
            "❌ 没有有效的 TG 权限\n"
            f"可用权限：all, {', '.join(TG_ALL_PERMS)}"
        )
        return

    # 构建 promote 参数：选中的设 True，未选的设 False
    promote_kwargs = {}
    for perm_key, (api_key, _) in TG_PERM_MAP.items():
        promote_kwargs[api_key] = perm_key in valid_tg

    try:
        await context.bot.promote_chat_member(chat_id, target.id, **promote_kwargs)
        perm_names = [_format_tg_perm(p) for p in sorted(valid_tg)]
        db.add_log(chat_id, update.effective_user.id, "set_tg_admin", target.id,
                   f"设置 {display} 为 TG 管理员，权限：{','.join(valid_tg)}")
        await update.effective_message.reply_text(
            f"✅ {display} 已设为 TG 管理员\n"
            f"TG 权限：{', '.join(perm_names)}"
        )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 设置 TG 管理员失败：{e}")


async def _remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list):
    """彻底移除管理员"""
    target = await _get_target_from_args(update, context, args)
    if not target:
        return

    chat_id = update.effective_chat.id
    display = target.username or target.first_name

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

    if was_custom:
        db.remove_custom_admin(chat_id, target.id)
        msg += "✅ Bot 管理员权限已移除\n"

    db.add_log(chat_id, update.effective_user.id, "remove_admin", target.id,
               f"取消 {display} 的管理员")
    await update.effective_message.reply_text(msg.strip())


# ─── Bot 权限管理命令 ───

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
    """格式化 Bot 权限列表"""
    if not perms:
        return "无"
    if perms == set(ALL_PERMISSIONS):
        return "全部"
    return ", ".join(PERM_LABELS.get(p, p) for p in sorted(perms))


def _format_tg_perm(perm_key: str) -> str:
    """格式化单个 TG 权限名称"""
    if perm_key in TG_PERM_MAP:
        return f"{perm_key}（{TG_PERM_MAP[perm_key][1]}）"
    return perm_key


def _parse_bot_perms(perm_args: list) -> set:
    """从参数中解析 Bot 权限（接收纯权限列表）"""
    valid_perms = set()
    for p in perm_args:
        p = p.lower().strip(",")
        if p in ALL_PERMISSIONS:
            valid_perms.add(p)

    # 指定 all → 全部权限
    if "all" in [p.lower() for p in perm_args]:
        valid_perms = set(ALL_PERMISSIONS)
    return valid_perms


async def _get_target_from_args(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list):
    """从参数列表中获取目标用户（支持回复消息或 user_id）"""
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    if args:
        try:
            uid = int(args[0])
            member = await context.bot.get_chat_member(update.effective_chat.id, uid)
            return member.user if hasattr(member, 'user') else member
        except (ValueError, Exception):
            pass
    await update.effective_message.reply_text("❌ 请回复目标用户的消息，或提供用户 ID")
    return None


async def _get_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """从 context.args 获取目标用户（兼容旧接口）"""
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