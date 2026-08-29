# =====================================================
# КОНФИГУРАЦИЯ DELTA VPN
# =====================================================

# =====================================================
# ТОКЕНЫ И КЛЮЧИ
# =====================================================

# Токен Telegram бота (получить у @BotFather)
BOT_TOKEN = "8731889904:AAH9bjm07c4LNos0PbZV34d3cm7Tfg78d5U"
# Токен Crypto Pay (получить у @CryptoBot)
CRYPTO_BOT_TOKEN = "627629:AA3qDjZ8zHNuOJrETVPCKq7yFFPPvD3omqx"

# Ключи Plateg8731889904:AAH9bjm07c4LNos0PbZV34d3cm7Tfg78d5U
PLATEGA_API_KEY = "ВАШ_КЛЮЧ_PLATEGA"
PLATEGA_API_URL = "https://api.platega.com"

# =====================================================
# АДМИНИСТРАТОРЫ (ОБНОВЛЕНО!)
# =====================================================

ADMIN_IDS = [
    8913219113,  # Админ 1
    8944641597   # Админ 2 (НОВЫЙ!)
]

# =====================================================
# ПОДДЕРЖКА
# =====================================================

SUPPORT_USERNAME = "chapez"          # Telegram username поддержки
SUPPORT_EMAIL = "deltavpn@inbox.eu"  # Email поддержки

# =====================================================
# БАЗА ДАННЫХ
# =====================================================

DB_PATH = "delta_bot.db"  # Путь к файлу базы данных SQLite

# =====================================================
# API ВОРКЕРА (CLOUDFLARE)
# =====================================================

WORKER_API_URL = "https://plain-limit-cb1c.delta-good.workers.dev"

# =====================================================
# ТАРИФЫ
# =====================================================

TARIFFS = {
    "3_devices": {
        "name": "🔥 3 устройства",
        "price": 500,
        "days": 36500,
        "max_devices": 3,
        "description": "✅ До 3 устройств одновременно\n✅ Доступ навсегда\n✅ Все сервера"
    },
    "5_devices": {
        "name": "🚀 5 устройств",
        "price": 650,
        "days": 36500,
        "max_devices": 5,
        "description": "✅ До 5 устройств одновременно\n✅ Доступ навсегда\n✅ Все сервера\n✅ Приоритетная поддержка"
    }
}

# =====================================================
# ССЫЛКИ ДЛЯ СКАЧИВАНИЯ HAPP
# =====================================================

HAPP_DOWNLOAD_LINKS = {
    "windows": "https://happ.info/download/windows",
    "iphone": "https://happ.info/download/ios",
    "android": "https://happ.info/download/android",
    "macos": "https://happ.info/download/macos",
    "linux": "https://happ.info/download/linux",
    "tv": "https://happ.info/download/tv"
}

# =====================================================
# ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ (URL)
# =====================================================

PRIVACY_POLICY_URL = "https://telegra.ph/Politika-konfidencialnosti-08-29-57"
TERMS_URL = "https://telegra.ph/Polzovatelskoe-soglashenie-08-29-36"

# =====================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================================

def require_config(name, value):
    if not value:
        raise ConfigurationError(f"Missing config: {name}")
    return value

class ConfigurationError(Exception):
    pass
