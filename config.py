import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DB_PATH = os.environ.get("DB_PATH", "data/bot.db")

# 默认配置（可通过 /settings 命令在群内动态调整）
DEFAULTS = {
    "warn_limit": 3,  # 警告次数上限，达到自动踢
    "new_user_mute_minutes": 5,  # 新用户静默期（分钟），0=关闭
    "flood_messages": 5,  # 洪水检测：N秒内发M条消息触发
    "flood_seconds": 5,
    "link_filter": False,  # 是否过滤链接
    "media_filter": False,  # 是否过滤媒体（图片/视频/贴纸等）
    "welcome_enabled": True,  # 是否启用欢迎消息
    "welcome_text": "欢迎 {user} 加入 {chat}！请先阅读群规：/rules",
    "goodbye_enabled": False,
    "goodbye_text": "{user} 离开了群组。",
    "rules_text": "暂未设置群规，管理员可使用 /setrules 设置。",
    "auto_delete_seconds": 0,  # 自动删除消息（秒），0=关闭
    "captcha_enabled": True,  # 新用户验证
    "captcha_timeout": 120,  # 验证超时（秒）
    "forward_filter": False,  # 是否过滤转发消息
    "auto_ban_on_leave": False,  # 用户主动退群时自动永久封禁
}
