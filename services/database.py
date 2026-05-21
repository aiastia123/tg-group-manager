"""SQLite 数据库服务"""
import sqlite3
import threading
import time
from contextlib import contextmanager
from config import DB_PATH, DEFAULTS
import os


_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


@contextmanager
def get_db():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                UNIQUE(chat_id, key)
            );

            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT DEFAULT '',
                admin_id INTEGER NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_id INTEGER DEFAULT 0,
                details TEXT DEFAULT '',
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_notes (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                note TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS blacklist (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT DEFAULT '',
                admin_id INTEGER NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS invite_links (
                chat_id INTEGER NOT NULL,
                link TEXT NOT NULL,
                creator_id INTEGER NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL DEFAULT 0,
                member_limit INTEGER DEFAULT 0,
                usage_count INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                PRIMARY KEY (chat_id, link)
            );

            CREATE TABLE IF NOT EXISTS invite_tracking (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                inviter_id INTEGER DEFAULT 0,
                link TEXT DEFAULT '',
                joined_at REAL NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS captcha (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                answer TEXT NOT NULL,
                token TEXT DEFAULT '',
                created_at REAL NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS muted (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                until REAL NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                reporter_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                message_id INTEGER DEFAULT 0,
                reason TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS flood_tracker (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                message_count INTEGER DEFAULT 0,
                last_message_at REAL NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS custom_admins (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                permissions TEXT DEFAULT '',
                added_by INTEGER NOT NULL,
                added_at REAL NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS pending_invites (
                token TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                link TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL DEFAULT 0,
                member_limit INTEGER DEFAULT 0,
                claimed INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sensitive_words (
                chat_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                added_by INTEGER NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (chat_id, word)
            );

            CREATE TABLE IF NOT EXISTS invite_permissions (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                max_invites INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                created_by INTEGER NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS pending_messages (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                claimed INTEGER DEFAULT 0
            );
        """)

        # 数据库迁移：为已有 captcha 表添加 token 列
        try:
            conn.execute("ALTER TABLE captcha ADD COLUMN token TEXT DEFAULT ''")
        except Exception:
            pass  # 列已存在，忽略

        # 数据库迁移：为已有 blacklist 表添加 expires_at 列
        try:
            conn.execute("ALTER TABLE blacklist ADD COLUMN expires_at REAL DEFAULT 0")
        except Exception:
            pass  # 列已存在，忽略


# ─── 配置管理 ───

def get_setting(chat_id: int, key: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM chat_settings WHERE chat_id=? AND key=?",
            (chat_id, key),
        ).fetchone()
        if row:
            return row["value"]
    return str(DEFAULTS.get(key, ""))


def get_settings(chat_id: int) -> dict:
    """获取群组的所有配置，合并默认值"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT key, value FROM chat_settings WHERE chat_id=?", (chat_id,)
        ).fetchall()
    settings = dict(DEFAULTS)
    for row in rows:
        key = row["key"]
        val = row["value"]
        # 类型转换
        if key in DEFAULTS:
            default_val = DEFAULTS[key]
            if isinstance(default_val, bool):
                val = val.lower() in ("true", "1", "yes")
            elif isinstance(default_val, int):
                val = int(val)
        settings[key] = val
    return settings


def set_setting(chat_id: int, key: str, value):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO chat_settings (chat_id, key, value) VALUES (?, ?, ?)",
            (chat_id, key, str(value)),
        )


# ─── 警告 ───

def add_warn(chat_id: int, user_id: int, reason: str, admin_id: int) -> int:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO warns (chat_id, user_id, reason, admin_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, reason, admin_id, time.time()),
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM warns WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()[0]
    return count


def get_warns(chat_id: int, user_id: int) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM warns WHERE chat_id=? AND user_id=? ORDER BY created_at DESC",
            (chat_id, user_id),
        ).fetchall()
    return [dict(r) for r in rows]


def clear_warns(chat_id: int, user_id: int) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
    return cur.rowcount


# ─── 操作日志 ───

def add_log(chat_id: int, admin_id: int, action: str, target_id: int = 0, details: str = ""):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO admin_log (chat_id, admin_id, action, target_id, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, admin_id, action, target_id, details, time.time()),
        )


def get_logs(chat_id: int, limit: int = 20) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM admin_log WHERE chat_id=? ORDER BY created_at DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ─── 用户备注 ───

def set_user_note(chat_id: int, user_id: int, note: str = "", tags: str = ""):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO user_notes (chat_id, user_id, note, tags) VALUES (?, ?, ?, ?)",
            (chat_id, user_id, note, tags),
        )


def get_user_note(chat_id: int, user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_notes WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()
    return dict(row) if row else None


# ─── 黑名单 ───

def add_blacklist(chat_id: int, user_id: int, reason: str, admin_id: int, expires_at: float = 0):
    """加入黑名单。expires_at > 0 表示定时自动解除，0 表示永久"""
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO blacklist (chat_id, user_id, reason, admin_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, reason, admin_id, time.time(), expires_at),
        )


def remove_blacklist(chat_id: int, user_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM blacklist WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
    return cur.rowcount > 0


def is_blacklisted(chat_id: int, user_id: int) -> bool:
    """检查是否在黑名单中（自动忽略已过期的记录）"""
    now = time.time()
    with get_db() as conn:
        row = conn.execute(
            "SELECT expires_at FROM blacklist WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()
        if row is None:
            return False
        # 如果设置了过期时间且已过期，则视为不在黑名单中
        if row["expires_at"] > 0 and row["expires_at"] <= now:
            conn.execute(
                "DELETE FROM blacklist WHERE chat_id=? AND user_id=?", (chat_id, user_id)
            )
            return False
        return True


def get_blacklist(chat_id: int) -> list:
    """获取黑名单列表（自动过滤已过期的记录）"""
    now = time.time()
    with get_db() as conn:
        # 先清理已过期的记录
        conn.execute(
            "DELETE FROM blacklist WHERE chat_id=? AND expires_at > 0 AND expires_at <= ?",
            (chat_id, now),
        )
        rows = conn.execute(
            "SELECT * FROM blacklist WHERE chat_id=? ORDER BY created_at DESC",
            (chat_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def cleanup_expired_blacklist():
    """清理所有群组中已过期的黑名单记录，返回过期的 (chat_id, user_id) 列表"""
    now = time.time()
    with get_db() as conn:
        # 先查询即将清理的记录，供调用方同步 Telegram 封禁
        rows = conn.execute(
            "SELECT chat_id, user_id FROM blacklist WHERE expires_at > 0 AND expires_at <= ?",
            (now,),
        ).fetchall()
        if rows:
            conn.execute(
                "DELETE FROM blacklist WHERE expires_at > 0 AND expires_at <= ?",
                (now,),
            )
        return [(r["chat_id"], r["user_id"]) for r in rows]


# ─── 邀请链接 ───

def save_invite_link(chat_id: int, link: str, creator_id: int, expires_at: float = 0, member_limit: int = 0):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO invite_links (chat_id, link, creator_id, created_at, expires_at, member_limit) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, link, creator_id, time.time(), expires_at, member_limit),
        )


def get_invite_links(chat_id: int, active_only: bool = True) -> list:
    with get_db() as conn:
        q = "SELECT * FROM invite_links WHERE chat_id=?"
        params: list = [chat_id]
        if active_only:
            q += " AND active=1"
        q += " ORDER BY created_at DESC"
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def deactivate_invite_link(chat_id: int, link: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE invite_links SET active=0 WHERE chat_id=? AND link=?",
            (chat_id, link),
        )


# ─── 邀请追踪 ───

def track_invite(chat_id: int, user_id: int, inviter_id: int = 0, link: str = ""):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO invite_tracking (chat_id, user_id, inviter_id, link, joined_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, inviter_id, link, time.time()),
        )


def get_invite_tracking(chat_id: int, user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM invite_tracking WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()
    return dict(row) if row else None


# ─── 验证码 ───

def save_captcha(chat_id: int, user_id: int, message_id: int, answer: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO captcha (chat_id, user_id, message_id, answer, created_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, message_id, answer, time.time()),
        )


def get_captcha(chat_id: int, user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM captcha WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def delete_captcha(chat_id: int, user_id: int):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM captcha WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )



def save_captcha_with_token(chat_id: int, user_id: int, message_id: int, answer: str, token: str):
    """保存验证码（含深链 token）"""
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO captcha (chat_id, user_id, message_id, answer, token, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, message_id, answer, token, time.time()),
        )


def get_captcha_by_token(token: str) -> dict | None:
    """通过深链 token 查找验证码"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM captcha WHERE token=?",
            (token,),
        ).fetchone()
    return dict(row) if row else None


def get_captcha_by_user(user_id: int) -> dict | None:
    """通过用户 ID 查找待验证记录"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM captcha WHERE user_id=? AND answer != 'pending'",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def update_captcha_answer(chat_id: int, user_id: int, answer: str):
    """更新验证码答案"""
    with get_db() as conn:
        conn.execute(
            "UPDATE captcha SET answer=? WHERE chat_id=? AND user_id=?",
            (answer, chat_id, user_id),
        )


def cleanup_expired_captchas(timeout: int = 300):
    """清理过期的验证码记录"""
    cutoff = time.time() - timeout
    with get_db() as conn:
        conn.execute("DELETE FROM captcha WHERE created_at < ?", (cutoff,))


# ─── 禁言 ───

def add_mute(chat_id: int, user_id: int, until: float):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO muted (chat_id, user_id, until) VALUES (?, ?, ?)",
            (chat_id, user_id, until),
        )


def remove_mute(chat_id: int, user_id: int):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM muted WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )


def is_muted(chat_id: int, user_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT until FROM muted WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()
    if row and row["until"] > time.time():
        return True
    return False


def cleanup_expired_mutes():
    """清理过期的禁言记录"""
    with get_db() as conn:
        conn.execute("DELETE FROM muted WHERE until <= ?", (time.time(),))


# ─── 举报 ───

def add_report(chat_id: int, reporter_id: int, target_id: int, reason: str, message_id: int = 0) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO reports (chat_id, reporter_id, target_id, message_id, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, reporter_id, target_id, message_id, reason, time.time()),
        )
        return cur.lastrowid


def get_reports(chat_id: int, status: str = "pending") -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM reports WHERE chat_id=? AND status=? ORDER BY created_at DESC LIMIT 20",
            (chat_id, status),
        ).fetchall()
    return [dict(r) for r in rows]


def update_report_status(report_id: int, status: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE reports SET status=? WHERE id=?", (status, report_id)
        )


# ─── 洪水追踪 ───

def check_flood(chat_id: int, user_id: int, max_messages: int, window_seconds: int) -> bool:
    """检查是否触发洪水，返回 True 表示触发"""
    now = time.time()
    with get_db() as conn:
        row = conn.execute(
            "SELECT message_count, last_message_at FROM flood_tracker WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO flood_tracker (chat_id, user_id, message_count, last_message_at) VALUES (?, ?, 1, ?)",
                (chat_id, user_id, now),
            )
            return False
        count = row["message_count"]
        last = row["last_message_at"]
        if now - last > window_seconds:
            conn.execute(
                "UPDATE flood_tracker SET message_count=1, last_message_at=? WHERE chat_id=? AND user_id=?",
                (now, chat_id, user_id),
            )
            return False
        count += 1
        conn.execute(
            "UPDATE flood_tracker SET message_count=?, last_message_at=? WHERE chat_id=? AND user_id=?",
            (count, now, chat_id, user_id),
        )
        return count >= max_messages


def reset_flood(chat_id: int, user_id: int):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM flood_tracker WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )


# ─── 自定义管理员 & 权限系统 ───

# 可分配的权限列表
ALL_PERMISSIONS = [
    "kick",      # 踢出用户
    "ban",       # 封禁/解封
    "mute",      # 禁言/解禁
    "warn",      # 警告
    "delete",    # 删除消息
    "pin",       # 置顶/取消置顶
    "invite",    # 管理邀请链接
    "admin",     # 管理其他管理员（含任命/撤职）
    "config",    # 修改群组配置
    "blacklist", # 黑名单管理
    "filter",    # 敏感词管理
    "logs",      # 查看操作日志
    "announce",  # 发布群公告
    "note",      # 用户备注/标签
]


def _parse_perms(permissions_str: str) -> set:
    """解析权限字符串为 set"""
    if not permissions_str:
        return set()
    return set(p.strip() for p in permissions_str.split(",") if p.strip() in ALL_PERMISSIONS)


def _perms_to_str(perms: set) -> str:
    """将权限 set 转为字符串存储"""
    return ",".join(sorted(perms))


def add_custom_admin(chat_id: int, user_id: int, added_by: int, permissions: str | set = ""):
    """添加自定义管理员。permissions 可以是逗号分隔字符串或 set，空字符串/空 set 表示全部权限"""
    if isinstance(permissions, set):
        perms_str = _perms_to_str(permissions) if permissions else _perms_to_str(set(ALL_PERMISSIONS))
    elif not permissions:
        perms_str = _perms_to_str(set(ALL_PERMISSIONS))
    else:
        perms_str = permissions
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO custom_admins (chat_id, user_id, permissions, added_by, added_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, perms_str, added_by, time.time()),
        )


def remove_custom_admin(chat_id: int, user_id: int):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM custom_admins WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )


def is_custom_admin(chat_id: int, user_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM custom_admins WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()
    return row is not None


def get_custom_admins(chat_id: int) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM custom_admins WHERE chat_id=?", (chat_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_admin_permissions(chat_id: int, user_id: int) -> set:
    """获取自定义管理员的具体权限集合。非自定义管理员返回空 set"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT permissions FROM custom_admins WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()
    if not row:
        return set()
    perms = _parse_perms(row["permissions"])
    # 如果权限为空，视为全部权限（兼容旧数据）
    return perms if perms else set(ALL_PERMISSIONS)


def set_admin_permissions(chat_id: int, user_id: int, perms: set):
    """直接设置管理员的权限"""
    perms_str = _perms_to_str(perms) if perms else _perms_to_str(set(ALL_PERMISSIONS))
    with get_db() as conn:
        conn.execute(
            "UPDATE custom_admins SET permissions=? WHERE chat_id=? AND user_id=?",
            (perms_str, chat_id, user_id),
        )


def admin_has_permission(chat_id: int, user_id: int, perm: str) -> bool:
    """检查自定义管理员是否拥有某个权限"""
    perms = get_admin_permissions(chat_id, user_id)
    return perm in perms


# ─── 普通用户邀请权限 ───

def set_invite_permission(chat_id: int, user_id: int, max_invites: int, created_by: int):
    """设置用户的邀请权限（user_id=0 表示 all）"""
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO invite_permissions (chat_id, user_id, max_invites, used_count, created_by, created_at) VALUES (?, ?, ?, 0, ?, ?)",
            (chat_id, user_id, max_invites, created_by, time.time()),
        )


def remove_invite_permission(chat_id: int, user_id: int) -> bool:
    """移除用户的邀请权限"""
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM invite_permissions WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
    return cur.rowcount > 0


def get_invite_permission(chat_id: int, user_id: int) -> dict | None:
    """获取用户的邀请权限（优先返回特定用户权限，其次返回 all 权限）"""
    with get_db() as conn:
        # 先查找特定用户的权限
        row = conn.execute(
            "SELECT * FROM invite_permissions WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()
        if row:
            return dict(row)
        # 再查找 all 权限（user_id=0）
        row = conn.execute(
            "SELECT * FROM invite_permissions WHERE chat_id=? AND user_id=0",
            (chat_id,),
        ).fetchone()
        if row:
            return dict(row)
    return None


def increment_invite_used(chat_id: int, user_id: int):
    """增加用户已使用的邀请次数"""
    with get_db() as conn:
        # 先尝试更新特定用户记录
        cur = conn.execute(
            "UPDATE invite_permissions SET used_count = used_count + 1 WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        )
        if cur.rowcount == 0:
            # 如果没有特定用户记录，更新 all 记录（user_id=0）
            conn.execute(
                "UPDATE invite_permissions SET used_count = used_count + 1 WHERE chat_id=? AND user_id=0",
                (chat_id,),
            )


def get_all_invite_permissions(chat_id: int) -> list:
    """获取群组所有邀请权限配置"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM invite_permissions WHERE chat_id=? ORDER BY user_id",
            (chat_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def remove_all_invite_permissions(chat_id: int) -> int:
    """移除群组的所有邀请权限配置（包括all）"""
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM invite_permissions WHERE chat_id=?", (chat_id,)
        )
    return cur.rowcount


# ─── 待领取邀请链接 ───

def save_pending_invite(token: str, chat_id: int, link: str, user_id: int, expires_at: float = 0, member_limit: int = 0):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO pending_invites (token, chat_id, link, user_id, created_at, expires_at, member_limit) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (token, chat_id, link, user_id, time.time(), expires_at, member_limit),
        )


def get_pending_invite(token: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM pending_invites WHERE token=? AND claimed=0",
            (token,),
        ).fetchone()
    return dict(row) if row else None


def claim_pending_invite(token: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE pending_invites SET claimed=1 WHERE token=?", (token,)
        )


# ─── 敏感词 ───

def add_sensitive_word(chat_id: int, word: str, added_by: int):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sensitive_words (chat_id, word, added_by, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, word, added_by, time.time()),
        )


def remove_sensitive_word(chat_id: int, word: str) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM sensitive_words WHERE chat_id=? AND word=?",
            (chat_id, word),
        )
    return cur.rowcount > 0


def get_sensitive_words(chat_id: int) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT word FROM sensitive_words WHERE chat_id=?", (chat_id,)
        ).fetchall()
    return [r["word"] for r in rows]


def contains_sensitive_word(chat_id: int, text: str) -> str | None:
    """检查文本是否包含敏感词
    - 普通模式：子串匹配
    - 通配符模式（含 * 或 ?）：fnmatch 匹配
    - 正则模式（re: 开头，如 re:\w+_[pvd]:[A-Za-z0-9]{32}）：re.search 搜索匹配
    """
    import fnmatch
    import re
    words = get_sensitive_words(chat_id)
    text_lower = text.lower()
    for w in words:
        w_lower = w.lower()
        # 正则模式：re:pattern
        if w_lower.startswith('re:') and len(w_lower) > 3:
            pattern = w[3:]  # 保留原始大小写用于正则
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    return w
            except re.error:
                pass  # 无效正则跳过
        elif '*' in w_lower or '?' in w_lower:
            # 通配符模式：拆分文本为单词逐一匹配，也尝试整体匹配
            if fnmatch.fnmatch(text_lower, w_lower):
                return w
            for word in text_lower.split():
                if fnmatch.fnmatch(word, w_lower):
                    return w
        else:
            # 普通模式：子串匹配
            if w_lower in text_lower:
                return w
    return None


# ─── 待领取的私聊消息（深链按钮模式） ───

def save_pending_message(token: str, user_id: int, content: str):
    """保存待私聊发送的消息"""
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO pending_messages (token, user_id, content, created_at, claimed) VALUES (?, ?, ?, ?, 0)",
            (token, user_id, content, time.time()),
        )


def get_pending_message(token: str) -> dict | None:
    """获取待领取的私聊消息"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM pending_messages WHERE token=? AND claimed=0",
            (token,),
        ).fetchone()
    return dict(row) if row else None


def claim_pending_message(token: str):
    """标记消息为已领取"""
    with get_db() as conn:
        conn.execute(
            "UPDATE pending_messages SET claimed=1 WHERE token=?", (token,)
        )


def cleanup_pending_messages(max_age: int = 3600):
    """清理过期的待领取消息（默认1小时）
    - 删除已领取的消息
    - 删除超过 max_age 秒未领取的消息
    """
    cutoff = time.time() - max_age
    with get_db() as conn:
        conn.execute(
            "DELETE FROM pending_messages WHERE claimed=1 OR created_at < ?",
            (cutoff,),
        )
