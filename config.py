# =====================================================
# КОНФИГУРАЦИЯ DELTA VPN
# =====================================================

# =====================================================
# ТОКЕНЫ
# =====================================================

# Токен Telegram бота (получить у @BotFather)
BOT_TOKEN = "8999084463:AAEiG6XkCKmzJlXp3PblPJay1pE_rpyhDwg"

# Токен Crypto Pay (получить у @CryptoBot)
CRYPTO_BOT_TOKEN = "627629:AA3qDjZ8zHNuOJrETVPCKq7yFFPPvD3omqx"

# Ключи Platega
PLATEGA_API_KEY = "ВАШ_КЛЮЧ_PLATEGA"
PLATEGA_API_URL = "https://api.platega.com"

# =====================================================
# АДМИНИСТРАТОРЫ
# =====================================================

ADMIN_IDS = [
    8913219113,   # Админ 1
    8944641597    # Админ 2
]

# =====================================================
# ПОДДЕРЖКА
# =====================================================

SUPPORT_USERNAME = "chapez"
SUPPORT_EMAIL = "deltavpn@inbox.eu"

# =====================================================
# БАЗА ДАННЫХ
# =====================================================

DB_PATH = "delta_bot.db"

# =====================================================
# WORKER API
# =====================================================

WORKER_API_URL = "https://rough-shadow-d067.delta-good.workers.dev"

# =====================================================
# ТАРИФЫ
# =====================================================

TARIFFS = {
    "3_devices_1m": {
        "name": "🔥 3 устройства (1 месяц)",
        "price": 240,
        "days": 30,
        "max_devices": 3,
        "description": "✅ До 3 устройств\n✅ 1 месяц\n✅ Все сервера"
    },
    "5_devices_1m": {
        "name": "🚀 5 устройств (1 месяц)",
        "price": 380,
        "days": 30,
        "max_devices": 5,
        "description": "✅ До 5 устройств\n✅ 1 месяц\n✅ Все сервера\n✅ Приоритетная поддержка"
    },
    "3_devices_3m": {
        "name": "🔥 3 устройства (3 месяца)",
        "price": 650,
        "days": 90,
        "max_devices": 3,
        "description": "✅ До 3 устройств\n✅ 3 месяца\n✅ Все сервера\n✅ Экономия 70 ₽"
    },
    "5_devices_3m": {
        "name": "🚀 5 устройств (3 месяца)",
        "price": 1000,
        "days": 90,
        "max_devices": 5,
        "description": "✅ До 5 устройств\n✅ 3 месяца\n✅ Все сервера\n✅ Приоритетная поддержка\n✅ Экономия 140 ₽"
    },
    # ========== ТЕСТОВЫЕ ТАРИФЫ (для админ-панели) ==========
    "3_devices_test": {
        "name": "🧪 3 устройства (тест 1 час)",
        "price": 0,
        "days": 0.04,  # 1 час = 0.04 дня
        "max_devices": 3,
        "description": "✅ Тестовая подписка на 1 час"
    },
    "5_devices_test": {
        "name": "🧪 5 устройств (тест 1 час)",
        "price": 0,
        "days": 0.04,  # 1 час = 0.04 дня
        "max_devices": 5,
        "description": "✅ Тестовая подписка на 1 час"
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
# ПОЛИТИКИ
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
