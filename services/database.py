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

            CREATE TABLE IF NOT EXISTS sensitive_words (
                chat_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                added_by INTEGER NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (chat_id, word)
            );
        """)


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

def add_blacklist(chat_id: int, user_id: int, reason: str, admin_id: int):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO blacklist (chat_id, user_id, reason, admin_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, reason, admin_id, time.time()),
        )


def remove_blacklist(chat_id: int, user_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM blacklist WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
    return cur.rowcount > 0


def is_blacklisted(chat_id: int, user_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM blacklist WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        ).fetchone()
    return row is not None


def get_blacklist(chat_id: int) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM blacklist WHERE chat_id=? ORDER BY created_at DESC",
            (chat_id,),
        ).fetchall()
    return [dict(r) for r in rows]


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


# ─── 自定义管理员 ───

def add_custom_admin(chat_id: int, user_id: int, added_by: int, permissions: str = ""):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO custom_admins (chat_id, user_id, permissions, added_by, added_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, permissions, added_by, time.time()),
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
    words = get_sensitive_words(chat_id)
    text_lower = text.lower()
    for w in words:
        if w.lower() in text_lower:
            return w
    return None
