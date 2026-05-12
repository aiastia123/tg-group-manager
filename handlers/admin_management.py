"""管理员设置 & 权限管理"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from utils.decorators import admin_required, require_perm, PERM_LABELS
from utils.private_reply import reply_private
from services import database as db
from services.database import ALL_PERMISSIONS

logger = logging.getLogger(__name__)

# TG 管理员权限映射（manage 是隐式基础权限，不暴露给用户）
TG_PERM_MAP = {
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
  none — 无权限（仅管理员头衔）
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
  announce（群公告）
  note（用户备注/标签）

━━━ TG 可用权限 ━━━
  all — 全部权限
  none — 无权限管理员（仅保留管理员头衔）
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
  /setadmin tg 123456 none — 无权限 TG 管理员（仅头衔）
  /setadmin bot 123456 none — 无权限 Bot 管理员
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

    # 检查是否是 none（无权限管理员）
    is_none = "none" in [p.lower() for p in perm_args]

    # 传入已计算好的 perm_args
    valid_perms = _parse_bot_perms(perm_args)

    if not is_none and not valid_perms:
        await update.effective_message.reply_text(
            "❌ 没有有效的 Bot 权限\n"
            f"可用权限：all, none, {', '.join(ALL_PERMISSIONS)}"
        )
        return

    if is_none:
        valid_perms = set()

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
            f"可用权限：all, none, {', '.join(TG_ALL_PERMS)}\n\n"
            "示例：\n"
            "  /setadmin tg 123456 all — 全部权限\n"
            "  /setadmin tg 123456 delete pin — 只能删消息和置顶"
        )
        return

    # 解析 TG 权限
    valid_tg = set()
    is_none = "none" in [p.lower() for p in perm_args]

    if not is_none:
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
                f"可用权限：all, none, {', '.join(TG_ALL_PERMS)}"
            )
            return

    # none = 无权限管理员（保留管理员头衔，仅 can_manage_chat=True）
    if is_none:
        try:
            await context.bot.promote_chat_member(
                chat_id, target.id,
                is_anonymous=False,
                can_manage_chat=True,
                can_post_messages=False,
                can_edit_messages=False,
                can_delete_messages=False,
                can_manage_video_chats=False,
                can_restrict_members=False,
                can_promote_members=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
                can_manage_topics=False,
            )
            db.add_log(chat_id, update.effective_user.id, "set_tg_admin", target.id,
                       f"设置 {display} 为无权限 TG 管理员（none）")
            await update.effective_message.reply_text(
                f"✅ {display} 已设为无权限 TG 管理员（仅保留管理员头衔）\n"
                f"💡 如需彻底移除管理员身份，请使用 /setadmin off"
            )
        except BadRequest as e:
            err_msg = str(e).lower()
            if "not enough rights" in err_msg or "bad request" in err_msg:
                await update.effective_message.reply_text(
                    f"❌ 设置失败：当前 Telegram 版本可能不支持无权限管理员\n"
                    f"📝 错误详情：{e}\n"
                    f"💡 请使用 /setadmin off 彻底移除管理员身份"
                )
            else:
                await update.effective_message.reply_text(f"❌ 操作失败：{e}")
        except Exception as e:
            await update.effective_message.reply_text(f"❌ 操作失败：{e}")
        return

    # 检查是否至少有一个权限（Telegram 要求管理员至少有一个真实权限）
    if not valid_tg:
        await update.effective_message.reply_text(
            "❌ 没有有效的 TG 权限\n"
            "Telegram 要求管理员至少拥有一个真实权限\n"
            f"可用权限：all, {', '.join(TG_ALL_PERMS)}"
        )
        return

    # 构建 promote 参数：can_manage_chat 是 TG 管理员基础权限，必须始终为 True
    has_delete = "delete" in valid_tg
    has_restrict = "restrict" in valid_tg
    has_invite = "invite" in valid_tg
    has_pin = "pin" in valid_tg
    has_video = "video" in valid_tg
    has_promote = "promote" in valid_tg
    has_info = "info" in valid_tg
    has_topics = "topics" in valid_tg

    try:
        # 记录请求的权限参数
        logger.info(
            "[set_tg_admin] 请求权限 chat=%s user=%s(%s) 请求: delete=%s pin=%s restrict=%s "
            "invite=%s video=%s promote=%s info=%s topics=%s",
            chat_id, display, target.id, has_delete, has_pin, has_restrict,
            has_invite, has_video, has_promote, has_info, has_topics
        )

        await context.bot.promote_chat_member(
            chat_id, target.id,
            is_anonymous=False,
            can_manage_chat=True,
            can_post_messages=False,
            can_edit_messages=False,
            can_delete_messages=has_delete,
            can_manage_video_chats=has_video,
            can_restrict_members=has_restrict,
            can_promote_members=has_promote,
            can_change_info=has_info,
            can_invite_users=has_invite,
            can_pin_messages=has_pin,
            can_manage_topics=has_topics,
        )

        # 读取实际权限确认设置成功
        actual_perms = await _get_actual_tg_perms(update.effective_chat, target.id)

        # 对比请求权限和实际权限
        extra = actual_perms - valid_tg
        missing = valid_tg - actual_perms

        logger.info(
            "[set_tg_admin] 权限对比 chat=%s user=%s(%s) 请求=%s 实际=%s 额外=%s 缺失=%s",
            chat_id, display, target.id,
            sorted(valid_tg), sorted(actual_perms),
            sorted(extra) if extra else "无",
            sorted(missing) if missing else "无"
        )

        perm_text = ', '.join(_format_tg_perm(p) for p in sorted(actual_perms))

        # 如果实际权限与请求不一致，追加提示
        warning = ""
        if extra or missing:
            parts = []
            if extra:
                parts.append(f"额外获得：{', '.join(_format_tg_perm(p) for p in sorted(extra))}")
            if missing:
                parts.append(f"未能生效：{', '.join(_format_tg_perm(p) for p in sorted(missing))}")
            warning = f"\n\n⚠️ 权限与请求不一致：\n" + "\n".join(f"  {p}" for p in parts)

        db.add_log(chat_id, update.effective_user.id, "set_tg_admin", target.id,
                   f"设置 {display} 为 TG 管理员，请求：{','.join(sorted(valid_tg))}，实际：{','.join(sorted(actual_perms))}")
        await update.effective_message.reply_text(
            f"✅ {display} 已设为 TG 管理员\n"
            f"TG 权限：{perm_text}"
            f"{warning}"
        )
    except Exception as e:
        logger.error("[set_tg_admin] 失败 chat=%s user=%s(%s) 错误: %s", chat_id, display, target.id, e)
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
            # 不传 can_manage_chat，让 Telegram 自动 demote（更兼容）
            await context.bot.promote_chat_member(
                chat_id, target.id,
                is_anonymous=False,
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
        except BadRequest:
            # 某些 TG 版本需要显式传 can_manage_chat=False
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
    """查看权限：/perms @user（分别显示 TG 权限和 Bot 权限）"""
    target = await _get_target(update, context)
    if not target:
        return

    chat_id = update.effective_chat.id
    display = target.username or target.first_name

    member = await update.effective_chat.get_member(target.id)

    msg = f"👤 {display} 的权限：\n"

    if member.status == "creator":
        msg += "\n🔹 身份：群主\n  拥有全部权限（TG + Bot）"
        await reply_private(update, context, msg, f"👤 {display} 的权限信息已准备好", "🔑 点击查看权限")
        return

    if member.status == "administrator":
        # 读取实际 TG 权限
        tg_perms = await _get_actual_tg_perms(update.effective_chat, target.id)
        msg += "\n🔹 身份：TG 管理员\n"
        if tg_perms:
            msg += "  TG 权限：" + "、".join(
                TG_PERM_MAP[p][1] for p in sorted(tg_perms) if p in TG_PERM_MAP
            ) + "\n"
        else:
            msg += "  TG 权限：无（仅管理员头衔）\n"

        # Bot 权限：检查是否有 Bot 管理员记录
        if db.is_custom_admin(chat_id, target.id):
            bot_perms = db.get_admin_permissions(chat_id, target.id)
            msg += f"  Bot 权限：{_format_perms(bot_perms)}"
        else:
            msg += "  Bot 权限：无（未通过 /setadmin bot 授权）"
        await reply_private(update, context, msg, f"👤 {display} 的权限信息已准备好", "🔑 点击查看权限")
        return

    # 普通用户 → 检查 Bot 自定义管理员权限
    if not db.is_custom_admin(chat_id, target.id):
        await update.effective_message.reply_text(f"❌ {display} 不是管理员")
        return

    perms = db.get_admin_permissions(chat_id, target.id)
    msg += "\n🔹 身份：Bot 管理员\n"
    if perms == set(ALL_PERMISSIONS):
        msg += "  Bot 权限：全部"
    else:
        for p in ALL_PERMISSIONS:
            mark = "✅" if p in perms else "❌"
            label = PERM_LABELS.get(p, p)
            msg += f"  {mark} {label}（{p}）\n"
    await reply_private(update, context, msg, f"👤 {display} 的权限信息已准备好", "🔑 点击查看权限")


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

        if admin.status == "creator":
            msg += f"  • {name}（群主）\n"
        else:
            # 读取实际 TG 权限
            tg_perms = set()
            perm_attr_map = {
                "delete": "can_delete_messages",
                "restrict": "can_restrict_members",
                "invite": "can_invite_users",
                "pin": "can_pin_messages",
                "video": "can_manage_video_chats",
                "promote": "can_promote_members",
                "info": "can_change_info",
                "topics": "can_manage_topics",
            }
            for key, attr in perm_attr_map.items():
                if getattr(admin, attr, False):
                    tg_perms.add(key)

            if tg_perms == set(TG_ALL_PERMS):
                perm_text = "全部权限"
            elif tg_perms:
                perm_text = "、".join(
                    TG_PERM_MAP[p][1] for p in sorted(tg_perms) if p in TG_PERM_MAP
                )
            else:
                perm_text = "无权限（仅头衔）"
            msg += f"  • {name}（{perm_text}）\n"

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

    await reply_private(update, context, msg, "📋 管理员列表已准备好，点击下方按钮私聊查看", "🛡️ 点击查看管理员")


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


async def _get_actual_tg_perms(chat, user_id: int) -> set:
    """从 Telegram 读取用户实际拥有的 TG 管理员权限"""
    member = await chat.get_member(user_id)
    actual = set()
    if member.status == "administrator":
        # TG ChatMember 对象的权限字段映射到我们的 key
        perm_attr_map = {
            "delete": "can_delete_messages",
            "restrict": "can_restrict_members",
            "invite": "can_invite_users",
            "pin": "can_pin_messages",
            "video": "can_manage_video_chats",
            "promote": "can_promote_members",
            "info": "can_change_info",
            "topics": "can_manage_topics",
        }
        for key, attr in perm_attr_map.items():
            if getattr(member, attr, False):
                actual.add(key)
    return actual


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