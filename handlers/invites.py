"""邀请链接管理"""
import secrets
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.decorators import admin_required, require_perm, is_user_admin, check_permission
from utils.private_reply import reply_private
from services import database as db


async def create_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """创建邀请链接：/invite [过期分钟] [使用次数]
    管理员：自由创建，可自定义参数。
    普通用户：需要管理员授权，链接 member_limit 由授权额度决定。
    """
    if not update.effective_user:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    is_admin = await check_permission(update, context, "invite")

    # ── 管理员逻辑：保持原有行为 ──
    if is_admin:
        expire_minutes = 60
        member_limit = 1

        if len(context.args) >= 1:
            try:
                expire_minutes = int(context.args[0])
            except ValueError:
                await update.effective_message.reply_text("❌ 过期时间必须是数字（分钟）")
                return
        if len(context.args) >= 2:
            try:
                member_limit = int(context.args[1])
            except ValueError:
                await update.effective_message.reply_text("❌ 使用次数必须是数字")
                return

        invite_link = await context.bot.create_chat_invite_link(
            chat_id,
            expire_date=int(time.time()) + expire_minutes * 60 if expire_minutes > 0 else None,
            member_limit=member_limit if member_limit > 0 else None,
        )

        db.save_invite_link(
            chat_id,
            invite_link.invite_link,
            user_id,
            expires_at=invite_link.expire_date.timestamp() if invite_link.expire_date else 0,
            member_limit=member_limit,
        )
        db.add_log(chat_id, user_id, "create_invite", details=f"创建邀请链接 {invite_link.invite_link}")

        # 生成唯一 token，保存待领取的邀请链接
        token = secrets.token_urlsafe(16)
        db.save_pending_invite(
            token=token,
            chat_id=chat_id,
            link=invite_link.invite_link,
            user_id=user_id,
            expires_at=invite_link.expire_date.timestamp() if invite_link.expire_date else 0,
            member_limit=member_limit,
        )

        # 构建深链按钮
        bot_username = context.bot.username
        deep_link = f"https://t.me/{bot_username}?start=invite_{token}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 点击获取邀请链接", url=deep_link)]
        ])

        msg = "✅ 邀请链接已创建"
        if expire_minutes:
            msg += f"\n有效期：{expire_minutes} 分钟"
        if member_limit:
            msg += f"\n使用次数：{member_limit}"
        msg += "\n\n👇 点击下方按钮获取链接"

        await update.effective_message.reply_text(msg, reply_markup=keyboard)
        return

    # ── 普通用户逻辑：检查邀请权限 ──
    perm = db.get_invite_permission(chat_id, user_id)
    if not perm:
        await update.effective_message.reply_text(
            "⛔ 你没有创建邀请链接的权限\n"
            "请联系管理员使用 /set_invite 授权"
        )
        return

    remaining = perm["max_invites"] - perm["used_count"]
    if remaining <= 0:
        await update.effective_message.reply_text(
            "❌ 你的邀请次数已用完\n"
            f"额度：{perm['max_invites']} 次，已使用：{perm['used_count']} 次"
        )
        return

    # 普通用户创建的链接，member_limit 固定为 1（每次邀请 1 人）
    invite_link = await context.bot.create_chat_invite_link(
        chat_id,
        member_limit=1,
    )

    db.save_invite_link(
        chat_id,
        invite_link.invite_link,
        user_id,
        expires_at=0,
        member_limit=1,
    )
    db.add_log(chat_id, user_id, "create_invite", details=f"普通用户创建邀请链接 {invite_link.invite_link}")

    # 增加已使用次数
    db.increment_invite_used(chat_id, user_id)

    # 生成唯一 token
    token = secrets.token_urlsafe(16)
    db.save_pending_invite(
        token=token,
        chat_id=chat_id,
        link=invite_link.invite_link,
        user_id=user_id,
        expires_at=0,
        member_limit=1,
    )

    bot_username = context.bot.username
    deep_link = f"https://t.me/{bot_username}?start=invite_{token}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 点击获取邀请链接", url=deep_link)]
    ])

    # 查询更新后的剩余次数
    updated_perm = db.get_invite_permission(chat_id, user_id)
    new_remaining = updated_perm["max_invites"] - updated_perm["used_count"] if updated_perm else 0

    msg = "✅ 邀请链接已创建（可邀请 1 人）"
    msg += f"\n📊 剩余邀请次数：{new_remaining} 次"
    msg += "\n\n👇 点击下方按钮获取链接"

    await update.effective_message.reply_text(msg, reply_markup=keyboard)


@require_perm("invite")
async def list_invites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看邀请链接：/invites"""
    chat_id = update.effective_chat.id
    links = db.get_invite_links(chat_id)

    if not links:
        await update.effective_message.reply_text("📭 没有邀请链接记录")
        return

    msg = "📋 邀请链接列表：\n\n"
    for i, link in enumerate(links[:10], 1):
        status = "🟢" if link["active"] else "🔴"
        msg += f"{i}. {status} {link['link']}\n"
        if link["member_limit"]:
            msg += f"   使用次数：{link['usage_count']}/{link['member_limit']}\n"

    await reply_private(update, context, msg, "📋 邀请链接列表已准备好，点击下方按钮私聊查看", "🔗 点击查看邀请链接")


@require_perm("invite")
async def revoke_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """撤销邀请链接：/revoke <链接>"""
    if not context.args:
        await update.effective_message.reply_text("用法：/revoke <邀请链接>")
        return

    link = context.args[0]
    chat_id = update.effective_chat.id

    try:
        await context.bot.revoke_chat_invite_link(chat_id, link)
        db.deactivate_invite_link(chat_id, link)
        db.add_log(chat_id, update.effective_user.id, "revoke_invite", details=f"撤销邀请链接 {link}")
        await update.effective_message.reply_text("✅ 邀请链接已撤销")
    except Exception as e:
        await update.effective_message.reply_text(f"❌ 撤销失败：{e}")


@require_perm("invite")
async def invite_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看谁邀请了谁：/whoinvited @user"""
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
        await update.effective_message.reply_text("用法：/whoinvited <用户ID或回复消息>")
        return

    chat_id = update.effective_chat.id
    info = db.get_invite_tracking(chat_id, target.id)
    display = target.username or target.first_name

    if not info:
        await update.effective_message.reply_text(f"📭 没有找到 {display} 的邀请记录")
        return

    msg = f"📋 {display} 的邀请信息：\n"
    if info["inviter_id"]:
        try:
            inviter = await context.bot.get_chat_member(chat_id, info["inviter_id"])
            inviter_name = inviter.user.username or inviter.user.first_name
            msg += f"邀请人：{inviter_name}\n"
        except Exception:
            msg += f"邀请人ID：{info['inviter_id']}\n"
    if info["link"]:
        msg += f"邀请链接：{info['link']}\n"

    await reply_private(update, context, msg, f"📋 {display} 的邀请信息已准备好，点击下方按钮私聊查看", "🔗 点击查看邀请信息")


@admin_required
async def set_invite_perm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员设置普通用户的邀请权限
    用法：
      /set_invite all [次数]           — 允许所有普通用户邀请，默认1人
      /set_invite <用户ID> [次数]       — 允许特定用户邀请，默认1人
      /set_invite off                   — 关闭所有普通用户的邀请权限
      /set_invite off <用户ID>          — 关闭特定用户的邀请权限
    """
    if not context.args:
        await update.effective_message.reply_text(
            "📌 **邀请权限设置**\n\n"
            "用法：\n"
            "• `/set_invite all [次数]` — 允许所有用户邀请，默认1人\n"
            "• `/set_invite <用户ID> [次数]` — 允许特定用户邀请，默认1人\n"
            "• `/set_invite off` — 关闭所有普通用户邀请权限\n"
            "• `/set_invite off <用户ID>` — 关闭特定用户邀请权限\n"
            "• `/set_invite list` — 查看当前邀请权限配置",
            parse_mode="Markdown",
        )
        return

    chat_id = update.effective_chat.id
    admin_id = update.effective_user.id
    action = context.args[0].lower()

    # ── 查看当前配置 ──
    if action == "list":
        perms = db.get_all_invite_permissions(chat_id)
        if not perms:
            await update.effective_message.reply_text("📭 当前没有设置任何邀请权限")
            return

        msg = "📋 **当前邀请权限配置：**\n\n"
        for p in perms:
            if p["user_id"] == 0:
                msg += f"🌐 **所有用户**：额度 {p['max_invites']} 次，已使用 {p['used_count']} 次\n"
            else:
                try:
                    member = await context.bot.get_chat_member(chat_id, p["user_id"])
                    name = member.user.username or member.user.first_name
                    display = f"@{name} (`{p['user_id']}`)"
                except Exception:
                    display = f"用户 `{p['user_id']}`"
                msg += f"👤 {display}：额度 {p['max_invites']} 次，已使用 {p['used_count']} 次\n"

        await update.effective_message.reply_text(msg, parse_mode="Markdown")
        return

    # ── 关闭权限 ──
    if action == "off":
        if len(context.args) >= 2:
            # 关闭特定用户
            try:
                target_id = int(context.args[1])
            except ValueError:
                await update.effective_message.reply_text("❌ 用户ID必须是数字")
                return
            removed = db.remove_invite_permission(chat_id, target_id)
            if removed:
                db.add_log(chat_id, admin_id, "set_invite_off", target_id=target_id, details=f"关闭用户 {target_id} 的邀请权限")
                await update.effective_message.reply_text(f"✅ 已关闭用户 `{target_id}` 的邀请权限", parse_mode="Markdown")
            else:
                await update.effective_message.reply_text("📭 该用户没有邀请权限记录")
        else:
            # 关闭所有
            count = db.remove_all_invite_permissions(chat_id)
            db.add_log(chat_id, admin_id, "set_invite_off", details=f"关闭所有普通用户邀请权限，清除 {count} 条记录")
            await update.effective_message.reply_text(f"✅ 已关闭所有普通用户的邀请权限（清除 {count} 条记录）")
        return

    # ── 设置权限 ──
    if action == "all":
        target_id = 0  # 0 代表所有用户
        max_invites = 1
        if len(context.args) >= 2:
            try:
                max_invites = int(context.args[1])
                if max_invites <= 0:
                    await update.effective_message.reply_text("❌ 邀请次数必须大于 0")
                    return
            except ValueError:
                await update.effective_message.reply_text("❌ 邀请次数必须是数字")
                return
        db.set_invite_permission(chat_id, 0, max_invites, admin_id)
        db.add_log(chat_id, admin_id, "set_invite_all", details=f"设置所有用户邀请额度为 {max_invites}")
        await update.effective_message.reply_text(
            f"✅ 已设置所有普通用户可邀请 **{max_invites}** 人\n"
            "普通用户使用 /invite 即可创建邀请链接",
            parse_mode="Markdown",
        )
        return

    # 特定用户
    try:
        target_id = int(action)
    except ValueError:
        await update.effective_message.reply_text(
            "❌ 无效参数\n请使用 `all`、`off`、`list` 或用户ID",
            parse_mode="Markdown",
        )
        return

    # 验证用户是否在群里
    try:
        member = await context.bot.get_chat_member(chat_id, target_id)
        if member.status in ("left", "kicked"):
            await update.effective_message.reply_text("❌ 该用户不在本群中")
            return
    except Exception:
        await update.effective_message.reply_text("❌ 无法找到该用户，请检查用户ID")
        return

    # 不能给管理员设置邀请权限（管理员本身就有权限）
    if await is_user_admin(update, context, target_id):
        await update.effective_message.reply_text("⚠️ 该用户是管理员，已经拥有邀请权限，无需额外设置")
        return

    max_invites = 1
    if len(context.args) >= 2:
        try:
            max_invites = int(context.args[1])
            if max_invites <= 0:
                await update.effective_message.reply_text("❌ 邀请次数必须大于 0")
                return
        except ValueError:
            await update.effective_message.reply_text("❌ 邀请次数必须是数字")
            return

    db.set_invite_permission(chat_id, target_id, max_invites, admin_id)

    target_name = member.user.username or member.user.first_name
    db.add_log(chat_id, admin_id, "set_invite_user", target_id=target_id, details=f"设置用户 {target_name} 邀请额度为 {max_invites}")

    await update.effective_message.reply_text(
        f"✅ 已设置用户 **{target_name}** (`{target_id}`) 可邀请 **{max_invites}** 人\n"
        "该用户现在可以使用 /invite 创建邀请链接",
        parse_mode="Markdown",
    )