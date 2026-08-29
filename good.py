import asyncio
import sqlite3
import datetime
import time
import logging
import json
import aiohttp
from typing import Optional, Tuple, List

if __package__:
    from .config import (
        ADMIN_IDS,
        BOT_TOKEN,
        CRYPTO_BOT_TOKEN,
        DB_PATH,
        HAPP_DOWNLOAD_LINKS,
        PLATEGA_API_KEY,
        PLATEGA_API_URL,
        SUPPORT_EMAIL,
        SUPPORT_USERNAME,
        TARIFFS,
        WORKER_API_URL,
        PRIVACY_POLICY_URL,
        TERMS_URL,
        ConfigurationError,
        require_config,
    )
else:
    from config import (
        ADMIN_IDS,
        BOT_TOKEN,
        CRYPTO_BOT_TOKEN,
        DB_PATH,
        HAPP_DOWNLOAD_LINKS,
        PLATEGA_API_KEY,
        PLATEGA_API_URL,
        SUPPORT_EMAIL,
        SUPPORT_USERNAME,
        TARIFFS,
        WORKER_API_URL,
        PRIVACY_POLICY_URL,
        TERMS_URL,
        ConfigurationError,
        require_config,
    )

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import requests

# =====================================================
# БАЗА ДАННЫХ (SQLite)
# =====================================================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            tariff TEXT,
            subscription_hash TEXT,
            max_devices INTEGER DEFAULT 3,
            until_date TEXT,
            paid INTEGER DEFAULT 0,
            manual_granted INTEGER DEFAULT 0,
            privacy_accepted INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            order_id TEXT,
            amount INTEGER,
            tariff TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            target_id INTEGER,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def fix_invalid_dates():
    """Исправляет некорректные даты в таблице users"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Находим все записи с некорректной датой
    cur.execute("SELECT user_id, until_date FROM users WHERE until_date IS NOT NULL AND until_date != 'нет'")
    rows = cur.fetchall()
    
    fixed_count = 0
    for user_id, until_date in rows:
        try:
            # Пробуем преобразовать в дату
            datetime.datetime.fromisoformat(until_date)
        except (ValueError, TypeError):
            # Если не дата — очищаем поле
            cur.execute("UPDATE users SET until_date = NULL, paid = 0 WHERE user_id = ?", (user_id,))
            fixed_count += 1
            print(f"🔧 Исправлен пользователь {user_id}: удалена некорректная дата '{until_date}'")
    
    conn.commit()
    conn.close()
    if fixed_count > 0:
        print(f"✅ Исправлено записей: {fixed_count}")
    return fixed_count

def get_user(user_id: int) -> Optional[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row

def create_user(user_id: int, username: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO users (user_id, username, paid, privacy_accepted) VALUES (?, ?, 0, 0)",
            (user_id, username)
        )
    conn.commit()
    conn.close()

def set_privacy_accepted(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET privacy_accepted = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_privacy_accepted(user_id: int) -> bool:
    user = get_user(user_id)
    if user and len(user) > 6:
        return user[6] == 1
    return False

def set_subscription(user_id: int, tariff_key: str, subscription_hash: str, max_devices: int, source: str = "auto"):
    # Проверяем, что tariff_key существует
    if tariff_key not in TARIFFS:
        tariff_key = "3_devices"  # значение по умолчанию
    
    # Вычисляем дату окончания
    until = (datetime.datetime.now() + datetime.timedelta(days=TARIFFS[tariff_key]["days"])).isoformat()
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """UPDATE users 
           SET tariff = ?, subscription_hash = ?, max_devices = ?, until_date = ?, paid = 1, manual_granted = ? 
           WHERE user_id = ?""",
        (tariff_key, subscription_hash, max_devices, until, 1 if source == "manual" else 0, user_id)
    )
    conn.commit()
    conn.close()

def revoke_subscription(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET paid = 0, until_date = NULL, subscription_hash = NULL, manual_granted = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def save_payment(user_id: int, order_id: str, amount: int, tariff: str, status: str = "pending"):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO payments (user_id, order_id, amount, tariff, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, order_id, amount, tariff, status, datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def update_payment_status(order_id: str, status: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE payments SET status = ? WHERE order_id = ?", (status, order_id))
    conn.commit()
    conn.close()

def log_admin_action(admin_id: int, action: str, target_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO admin_logs (admin_id, action, target_id, timestamp) VALUES (?, ?, ?, ?)",
        (admin_id, action, target_id, datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_all_users() -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, tariff, until_date, paid, manual_granted, privacy_accepted, subscription_hash, max_devices FROM users ORDER BY user_id")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_active_subscriptions() -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cur.execute("""
        SELECT user_id, username, tariff, until_date, manual_granted, subscription_hash, max_devices
        FROM users 
        WHERE paid = 1 AND until_date > ?
        ORDER BY until_date
    """, (now,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_paid_users() -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, username, tariff, until_date, subscription_hash, max_devices, manual_granted
        FROM users 
        WHERE paid = 1
        ORDER BY until_date DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

def is_subscription_active(user_id: int) -> bool:
    user = get_user(user_id)
    if not user:
        return False
    if len(user) < 4:
        return False
    until = user[3]
    if not until:
        return False
    try:
        until_date = datetime.datetime.fromisoformat(until)
        return until_date > datetime.datetime.now()
    except (ValueError, TypeError):
        return False

# =====================================================
# РАБОТА С API ВОРКЕРА
# =====================================================

async def create_subscription(max_devices: int, note: str = "") -> dict:
    url = f"{WORKER_API_URL}/api/create"
    headers = {"Content-Type": "application/json"}
    
    data = {
        "max_devices": max_devices,
        "note": note
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            if response.status == 200:
                result = await response.json()
                if result.get("ok"):
                    return result
                else:
                    raise Exception(f"API error: {result.get('error', 'Unknown error')}")
            else:
                error_text = await response.text()
                raise Exception(f"API error {response.status}: {error_text}")

async def get_subscription_info(hash_id: str) -> dict:
    url = f"{WORKER_API_URL}/api/info/{hash_id}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise Exception(f"API error {response.status}")

async def reset_devices(hash_id: str) -> dict:
    url = f"{WORKER_API_URL}/api/reset/{hash_id}"
    
    async with aiohttp.ClientSession() as session:
        async with session.delete(url) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise Exception(f"API error {response.status}")

# =====================================================
# ПЛАТЕЖИ
# =====================================================

def create_platega_payment(amount: int, user_id: int, tariff: str) -> dict:
    require_config("PLATEGA_API_KEY", PLATEGA_API_KEY)
    order_id = f"order_{user_id}_{int(time.time())}"
    payload = {
        "amount": amount,
        "currency": "RUB",
        "description": f"Delta VPN {TARIFFS[tariff]['name']} для {user_id}",
        "order_id": order_id,
        "success_url": "https://t.me/delta_bot?start=success",
        "fail_url": "https://t.me/delta_bot?start=fail",
        "callback_url": "https://your-server.com/webhook/platega"
    }
    headers = {
        "Authorization": f"Bearer {PLATEGA_API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.post(
        f"{PLATEGA_API_URL}/payments",
        json=payload,
        headers=headers,
        timeout=30
    )
    if 200 <= response.status_code < 300:
        data = response.json()
        return {
            "payment_url": data.get("payment_url"),
            "order_id": order_id
        }
    else:
        raise Exception(f"Platega ошибка: {response.status_code} - {response.text}")

def create_crypto_payment(amount_rub: int, user_id: int, tariff: str) -> dict:
    require_config("CRYPTO_BOT_TOKEN", CRYPTO_BOT_TOKEN)
    order_id = f"crypto_{user_id}_{int(time.time())}"
    usdt_amount = round(amount_rub / 100, 2)
    if usdt_amount < 1:
        usdt_amount = 1
    payload = {
        "asset": "USDT",
        "amount": str(usdt_amount),
        "description": f"Delta VPN {TARIFFS[tariff]['name']}",
        "payload": order_id,
        "paid_btn_name": "openBot",
        "paid_btn_url": "https://t.me/delta_bot"
    }
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    response = requests.post(
        "https://pay.crypt.bot/api/createInvoice",
        json=payload,
        headers=headers,
        timeout=30
    )
    if response.status_code == 200:
        data = response.json()
        if data.get("ok"):
            invoice = data["result"]
            save_payment(user_id, order_id, amount_rub, tariff, "pending_crypto")
            return {
                "payment_url": invoice.get("pay_url"),
                "order_id": order_id,
                "invoice_id": invoice.get("invoice_id")
            }
        else:
            raise Exception(f"CryptoBot ошибка: {data}")
    else:
        raise Exception(f"CryptoBot ошибка: {response.status_code} - {response.text}")

def check_crypto_payment(invoice_id: int) -> str:
    require_config("CRYPTO_BOT_TOKEN", CRYPTO_BOT_TOKEN)
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    params = {"invoice_ids": invoice_id}
    response = requests.get(
        "https://pay.crypt.bot/api/getInvoices",
        params=params,
        headers=headers,
        timeout=30
    )
    if response.status_code != 200:
        raise RuntimeError(f"CryptoBot ошибка: {response.status_code} - {response.text}")

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"CryptoBot ошибка: {data}")

    invoices = data.get("result", {}).get("items", [])
    if not invoices:
        raise RuntimeError("CryptoBot не вернул счет с таким invoice_id.")

    status = invoices[0].get("status")
    if status == "paid":
        return "paid"
    if status in {"expired", "cancelled"}:
        return "failed"
    return "pending"

def check_platega_payment(order_id: str) -> str:
    require_config("PLATEGA_API_KEY", PLATEGA_API_KEY)
    headers = {"Authorization": f"Bearer {PLATEGA_API_KEY}"}
    response = requests.get(
        f"{PLATEGA_API_URL}/payments/{order_id}",
        headers=headers,
        timeout=30,
    )
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"Platega ошибка: {response.status_code} - {response.text}")

    status = response.json().get("status")
    if not status:
        raise RuntimeError("Platega не вернул статус платежа.")
    return status

# =====================================================
# FSM СОСТОЯНИЯ
# =====================================================

class AdminStates(StatesGroup):
    awaiting_grant_id = State()
    awaiting_revoke_id = State()

class PrivacyStates(StatesGroup):
    waiting_acceptance = State()

# =====================================================
# КЛАВИАТУРЫ
# =====================================================

def privacy_accept_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📄 Политика конфиденциальности",
                    url=PRIVACY_POLICY_URL
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Пользовательское соглашение",
                    url=TERMS_URL
                )
            ],
            [InlineKeyboardButton(text="✅ Согласиться", callback_data="accept_privacy")],
        ]
    )

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Купить доступ", callback_data="buy")],
            [InlineKeyboardButton(text="ℹ️ О Delta", callback_data="about")],
            [InlineKeyboardButton(text="📄 Документы", callback_data="documents")],
            [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
            [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")],
        ]
    )

def tariffs_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🔥 3 устройства — 500 ₽",
                    callback_data="tariff_3_devices"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🚀 5 устройств — 650 ₽",
                    callback_data="tariff_5_devices"
                )
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")],
        ]
    )

def payment_methods_keyboard(tariff: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💳 Карта / СБП", callback_data=f"pay_card_{tariff}"),
                InlineKeyboardButton(text="🪙 Крипто (USDT)", callback_data=f"pay_crypto_{tariff}"),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="buy")],
        ]
    )

def documents_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📄 Политика конфиденциальности",
                    callback_data="show_privacy"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Пользовательское соглашение",
                    callback_data="show_terms"
                )
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")],
        ]
    )

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Все пользователи", callback_data="admin_users")],
            [InlineKeyboardButton(text="✅ Активные подписки", callback_data="admin_active")],
            [InlineKeyboardButton(text="💰 Платные пользователи", callback_data="admin_paid")],
            [InlineKeyboardButton(text="➕ Выдать подписку", callback_data="admin_grant")],
            [InlineKeyboardButton(text="❌ Отозвать подписку", callback_data="admin_revoke")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="📋 Логи", callback_data="admin_logs")],
            [InlineKeyboardButton(text="🔙 Выход", callback_data="back")],
        ]
    )

def admin_users_keyboard(users: list, page: int = 0) -> InlineKeyboardMarkup:
    per_page = 10
    start = page * per_page
    end = min(start + per_page, len(users))
    rows = []
    for user in users[start:end]:
        user_id, username, tariff, until, paid, manual, privacy, sub_hash, max_dev = user
        status = "✅" if paid and until and until > datetime.datetime.now().isoformat() else "❌"
        rows.append([
            InlineKeyboardButton(
                text=f"{status} {user_id} (@{username or 'no_name'})",
                callback_data=f"admin_user_{user_id}",
            )
        ])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_users_page_{page-1}"))
    if end < len(users):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"admin_users_page_{page+1}"))
    if nav_buttons:
        rows.append(nav_buttons)
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_paid_keyboard(users: list, page: int = 0) -> InlineKeyboardMarkup:
    per_page = 10
    start = page * per_page
    end = min(start + per_page, len(users))
    rows = []
    for user in users[start:end]:
        user_id, username, tariff, until, sub_hash, max_dev, manual = user
        try:
            until_date = datetime.datetime.fromisoformat(until)
            remaining = (until_date - datetime.datetime.now()).days
        except (ValueError, TypeError):
            remaining = 0
        rows.append([
            InlineKeyboardButton(
                text=f"👤 {user_id} (@{username or 'no_name'}) — {tariff} ({remaining} дн.)",
                callback_data=f"admin_user_{user_id}",
            )
        ])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_paid_page_{page-1}"))
    if end < len(users):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"admin_paid_page_{page+1}"))
    if nav_buttons:
        rows.append(nav_buttons)
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def device_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💻 Windows", callback_data="device_windows"),
                InlineKeyboardButton(text="🍎 iPhone / iPad", callback_data="device_iphone"),
            ],
            [
                InlineKeyboardButton(text="🤖 Android", callback_data="device_android"),
                InlineKeyboardButton(text="🖥 macOS", callback_data="device_macos"),
            ],
            [
                InlineKeyboardButton(text="🐧 Linux", callback_data="device_linux"),
                InlineKeyboardButton(text="📺 TV", callback_data="device_tv"),
            ],
        ]
    )

def delivered_connection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Выбрать другое устройство", callback_data="choose_device")],
            [InlineKeyboardButton(text="ℹ️ О Delta", callback_data="about")],
        ]
    )

def device_connection_text(device_key: str, subscription_url: str) -> str:
    devices = {
        "windows": ("ПК на Windows", "Откройте скачанный установщик и установите HAPP."),
        "iphone": ("iPhone / iPad", "Установите HAPP из App Store и откройте приложение."),
        "android": ("Android", "Установите HAPP из Google Play и откройте приложение."),
        "macos": ("macOS", "Откройте скачанный файл и установите HAPP."),
        "linux": ("Linux", "Скачайте пакет для Linux и установите HAPP."),
        "tv": ("Android TV", "Установите HAPP на телевизор через Google Play."),
    }
    device = devices.get(device_key)
    download_url = HAPP_DOWNLOAD_LINKS.get(device_key)
    if not device or not download_url:
        raise ValueError("Неизвестное устройство.")

    device_name, install_step = device
    return (
        f"✅ **Подписка активна!**\n\n"
        f"📱 **Устройство: {device_name}**\n\n"
        f"1️⃣ [Скачать HAPP]({download_url})\n"
        f"2️⃣ {install_step}\n"
        "3️⃣ Нажмите **+** в приложении\n"
        "4️⃣ Вставьте ссылку из блока ниже\n\n"
        f"🔗 **Ваша VPN-ссылка:**\n`{subscription_url}`\n\n"
        "⚠️ Ссылка активна для **до 3 устройств**\n"
        "После добавления ссылки включите соединение в HAPP."
    )

# =====================================================
# БОТ
# =====================================================

dp = Dispatcher(storage=MemoryStorage())

# =====================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ
# =====================================================

async def show_main_menu(message: Message, user_id: int):
    if is_subscription_active(user_id):
        user = get_user(user_id)
        subscription_url = user[7] if user and len(user) > 7 else None
        
        if subscription_url:
            text = (
                "🚀 **Delta VPN — ускоритель интернета**\n\n"
                "✅ У вас активная подписка **навсегда**!\n\n"
                "Выберите устройство для подключения:"
            )
            await message.answer(text, parse_mode="Markdown", reply_markup=device_selection_keyboard())
        else:
            text = (
                "🚀 **Delta VPN — ускоритель интернета**\n\n"
                "⚠️ У вас активная подписка, но нет ссылки.\n"
                f"Обратитесь в поддержку: @{SUPPORT_USERNAME}"
            )
            await message.answer(text, parse_mode="Markdown")
    else:
        text = (
            "🚀 **Delta VPN — ускоритель интернета**\n\n"
            "Добро пожаловать! Выберите тариф:\n\n"
            "🔥 **3 устройства** — 500 ₽\n"
            "🚀 **5 устройств** — 650 ₽\n\n"
            "💳 Оплата: карта, СБП, криптовалюта\n"
            "📱 Работает через HAPP\n"
            "📌 Все документы доступны по кнопкам ниже."
        )
        await message.answer(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

# =====================================================
# ХЕНДЛЕРЫ КОМАНД
# =====================================================

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"
    create_user(user_id, username)
    
    if not is_privacy_accepted(user_id):
        await state.set_state(PrivacyStates.waiting_acceptance)
        text = (
            "🔒 **Для использования Delta VPN необходимо принять условия**\n\n"
            "Пожалуйста, ознакомьтесь с документами и нажмите «Согласиться»:\n\n"
            f"📄 [Политика конфиденциальности]({PRIVACY_POLICY_URL})\n"
            f"📋 [Пользовательское соглашение]({TERMS_URL})\n\n"
            "Нажимая «Согласиться», вы подтверждаете, что ознакомились "
            "и принимаете оба документа в полном объёме."
        )
        await message.answer(
            text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=privacy_accept_keyboard()
        )
        return
    
    await show_main_menu(message, user_id)

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return
    text = "🔧 **Админ-панель Delta VPN**\n\nВыберите действие:"
    await message.answer(text, parse_mode="Markdown", reply_markup=admin_menu_keyboard())

@dp.message(Command("check"))
async def cmd_check(message: Message):
    user_id = message.from_user.id
    if is_subscription_active(user_id):
        user = get_user(user_id)
        try:
            until = datetime.datetime.fromisoformat(user[3])
            remaining = (until - datetime.datetime.now()).days
        except (ValueError, TypeError):
            remaining = 0
        tariff = user[2] or "не выбран"
        max_dev = user[8] or 3
        await message.answer(
            f"✅ **Ваша подписка активна**\n\n"
            f"📦 Тариф: {tariff}\n"
            f"📱 Устройств: {max_dev}\n"
            f"📅 Осталось дней: {remaining}\n"
            f"🔗 Ссылка: {user[7] or 'не выдана'}"
        )
    else:
        await message.answer("❌ У вас нет активной подписки. Купите за 500 ₽.")

@dp.message(Command("privacy"))
@dp.message(Command("policy"))
async def cmd_privacy(message: Message):
    await message.answer(
        f"📄 **Политика конфиденциальности Delta VPN**\n\n"
        f"Полный текст документа доступен по ссылке:\n"
        f"🔗 {PRIVACY_POLICY_URL}",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

@dp.message(Command("terms"))
async def cmd_terms(message: Message):
    await message.answer(
        f"📋 **Пользовательское соглашение Delta VPN**\n\n"
        f"Полный текст документа доступен по ссылке:\n"
        f"🔗 {TERMS_URL}",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

@dp.message(Command("support"))
async def cmd_support(message: Message):
    text = (
        f"🆘 **Поддержка Delta VPN**\n\n"
        f"📱 Telegram: [@{SUPPORT_USERNAME}](https://t.me/{SUPPORT_USERNAME})\n"
        f"📧 Email: {SUPPORT_EMAIL}\n"
        "⏱️ Время ответа: 1-2 часа\n\n"
        "❓ Частые вопросы:\n"
        "• Как подключиться? → /start\n"
        "• Проверить подписку → /check\n"
        "• Документы → кнопка «Документы»"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📩 Написать в поддержку",
                    url=f"https://t.me/{SUPPORT_USERNAME}"
                )
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
        ]
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

# =====================================================
# КОЛБЭКИ
# =====================================================

@dp.callback_query(F.data == "accept_privacy", PrivacyStates.waiting_acceptance)
async def accept_privacy(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    set_privacy_accepted(user_id)
    await state.clear()
    
    await callback.message.edit_text(
        "✅ **Вы согласились с условиями!**\n\n"
        "Загружаем главное меню...",
        parse_mode="Markdown"
    )
    
    await show_main_menu(callback.message, user_id)
    await callback.answer()

@dp.callback_query(F.data == "back")
async def back_to_main(callback: CallbackQuery):
    user_id = callback.from_user.id
    await show_main_menu(callback.message, user_id)
    await callback.answer()

@dp.callback_query(F.data == "buy")
async def buy_subscription(callback: CallbackQuery):
    text = (
        "🚀 **Выберите тариф:**\n\n"
        "🔥 **3 устройства** — 500 ₽\n"
        "   • До 3 устройств одновременно\n"
        "   • Доступ навсегда\n"
        "   • Все сервера\n\n"
        "🚀 **5 устройств** — 650 ₽\n"
        "   • До 5 устройств одновременно\n"
        "   • Доступ навсегда\n"
        "   • Все сервера\n"
        "   • Приоритетная поддержка"
    )
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=tariffs_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("tariff_"))
async def select_tariff(callback: CallbackQuery):
    tariff_key = callback.data.replace("tariff_", "")
    if tariff_key not in TARIFFS:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return
    
    tariff = TARIFFS[tariff_key]
    text = (
        f"💰 **Вы выбрали тариф: {tariff['name']}**\n\n"
        f"📦 Стоимость: **{tariff['price']} ₽**\n"
        f"📱 Устройств: {tariff['max_devices']}\n"
        f"📅 Срок: **навсегда**\n\n"
        f"{tariff['description']}\n\n"
        "Выберите способ оплаты:"
    )
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=payment_methods_keyboard(tariff_key)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("pay_card_"))
async def pay_card(callback: CallbackQuery):
    tariff_key = callback.data.replace("pay_card_", "")
    user_id = callback.from_user.id
    tariff = TARIFFS[tariff_key]
    
    try:
        create_user(user_id, callback.from_user.username or "unknown")
        result = await asyncio.to_thread(
            create_platega_payment,
            tariff["price"],
            user_id,
            tariff_key
        )
        payment_url = result.get("payment_url")
        order_id = result.get("order_id")
        if not payment_url or not order_id:
            raise RuntimeError("Platega не вернул ссылку")
        
        save_payment(user_id, order_id, tariff["price"], tariff_key, "pending")
        
        text = (
            f"💳 **Оплата картой / СБП**\n\n"
            f"📦 Тариф: {tariff['name']}\n"
            f"💰 Сумма: {tariff['price']} ₽\n\n"
            f"🔗 [Перейти к оплате]({payment_url})\n\n"
            "✅ После оплаты подписка активируется автоматически.\n"
            "⏱️ Обычно занимает 1-2 минуты."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Проверить оплату",
                        callback_data=f"check_payment_{order_id}_{tariff_key}",
                    )
                ],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="buy")],
            ]
        )
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}")
        logging.error(f"Payment error: {e}")
    await callback.answer()

@dp.callback_query(F.data.startswith("pay_crypto_"))
async def pay_crypto(callback: CallbackQuery):
    tariff_key = callback.data.replace("pay_crypto_", "")
    user_id = callback.from_user.id
    tariff = TARIFFS[tariff_key]
    
    try:
        create_user(user_id, callback.from_user.username or "unknown")
        result = await asyncio.to_thread(
            create_crypto_payment,
            tariff["price"],
            user_id,
            tariff_key
        )
        payment_url = result.get("payment_url")
        invoice_id = result.get("invoice_id")
        if not payment_url or not invoice_id:
            raise RuntimeError("CryptoBot не вернул ссылку")
        
        text = (
            f"🪙 **Оплата криптовалютой (USDT)**\n\n"
            f"📦 Тариф: {tariff['name']}\n"
            f"💰 Сумма: ~{round(tariff['price']/100, 2)} USDT\n\n"
            f"🔗 [Перейти к оплате]({payment_url})\n\n"
            "✅ Оплата подтвердится после 3 подтверждений в сети.\n"
            "⏱️ Обычно занимает 5-15 минут."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Проверить оплату",
                        callback_data=f"check_crypto_{invoice_id}_{tariff_key}",
                    )
                ],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="buy")],
            ]
        )
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}")
        logging.error(f"Crypto payment error: {e}")
    await callback.answer()

@dp.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.replace("check_payment_", "").split("_")
    order_id = parts[0]
    tariff_key = parts[1] if len(parts) > 1 else "3_devices"
    
    try:
        status = await asyncio.to_thread(check_platega_payment, order_id)
        update_payment_status(order_id, status)

        if status == "paid":
            max_devices = TARIFFS[tariff_key]["max_devices"]
            result = await create_subscription(max_devices, f"user_{user_id}")
            subscription_hash = result.get("hash")
            subscription_url = result.get("subscription_url")
            
            if subscription_hash and subscription_url:
                set_subscription(user_id, tariff_key, subscription_hash, max_devices, "auto")
                
                text = (
                    f"✅ **Оплата подтверждена!**\n\n"
                    f"Подписка **{TARIFFS[tariff_key]['name']}** активирована.\n\n"
                    "Выберите устройство для подключения:"
                )
                await callback.message.edit_text(
                    text,
                    parse_mode="Markdown",
                    reply_markup=device_selection_keyboard()
                )
                await callback.answer("✅ Подписка активирована!")
            else:
                await callback.answer("❌ Ошибка создания подписки", show_alert=True)
        elif status == "pending":
            await callback.answer("⏳ Платеж еще обрабатывается. Подождите 1-2 минуты.", show_alert=True)
        else:
            await callback.answer(f"❌ Платеж не прошел. Статус: {status}", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("check_crypto_"))
async def check_crypto(callback: CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.replace("check_crypto_", "").split("_")
    invoice_id = int(parts[0])
    tariff_key = parts[1] if len(parts) > 1 else "3_devices"
    
    try:
        status = await asyncio.to_thread(check_crypto_payment, invoice_id)
        if status == "paid":
            max_devices = TARIFFS[tariff_key]["max_devices"]
            result = await create_subscription(max_devices, f"user_{user_id}")
            subscription_hash = result.get("hash")
            subscription_url = result.get("subscription_url")
            
            if subscription_hash and subscription_url:
                set_subscription(user_id, tariff_key, subscription_hash, max_devices, "auto")
                
                text = (
                    f"✅ **Оплата криптовалютой подтверждена!**\n\n"
                    f"Подписка **{TARIFFS[tariff_key]['name']}** активирована.\n\n"
                    "Выберите устройство для подключения:"
                )
                await callback.message.edit_text(
                    text,
                    parse_mode="Markdown",
                    reply_markup=device_selection_keyboard()
                )
                await callback.answer("✅ Подписка активирована!")
            else:
                await callback.answer("❌ Ошибка создания подписки", show_alert=True)
        elif status == "pending":
            await callback.answer("⏳ Платеж еще обрабатывается. Проверьте через 5-10 минут.", show_alert=True)
        else:
            await callback.answer("❌ Платеж не прошел или истек.", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@dp.callback_query(F.data == "documents")
async def show_documents_menu(callback: CallbackQuery):
    text = "📚 **Документы Delta VPN**\n\nВыберите документ для ознакомления:"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=documents_menu_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "show_privacy")
async def show_privacy(callback: CallbackQuery):
    text = (
        f"📄 **Политика конфиденциальности Delta VPN**\n\n"
        f"Полный текст документа доступен по ссылке:\n"
        f"🔗 {PRIVACY_POLICY_URL}"
    )
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="documents")]
            ]
        )
    )
    await callback.answer()

@dp.callback_query(F.data == "show_terms")
async def show_terms(callback: CallbackQuery):
    text = (
        f"📋 **Пользовательское соглашение Delta VPN**\n\n"
        f"Полный текст документа доступен по ссылке:\n"
        f"🔗 {TERMS_URL}"
    )
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="documents")]
            ]
        )
    )
    await callback.answer()

@dp.callback_query(F.data == "about")
async def about_delta(callback: CallbackQuery):
    text = (
        "🚀 **О Delta VPN**\n\n"
        "Delta VPN — это ускоритель интернета, который позволяет:\n"
        "✅ Обходить региональные ограничения\n"
        "✅ Увеличивать скорость доступа\n"
        "✅ Обеспечивать безопасное соединение\n\n"
        "🔒 Без логов, высокая скорость, серверы в 10 странах.\n"
        "💳 Оплата разовая — доступ **навсегда**.\n\n"
        "📱 Работает с HAPP: https://happ.info/"
    )
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
            ]
        )
    )
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support_delta(callback: CallbackQuery):
    text = (
        f"🆘 **Поддержка Delta VPN**\n\n"
        f"📱 Telegram: [@{SUPPORT_USERNAME}](https://t.me/{SUPPORT_USERNAME})\n"
        f"📧 Email: {SUPPORT_EMAIL}\n"
        "⏱️ Время ответа: 1-2 часа\n\n"
        "❓ Частые вопросы:\n"
        "• Как подключиться? → /start\n"
        "• Проверить подписку → /check\n"
        "• Документы → кнопка «Документы»"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📩 Написать в поддержку",
                    url=f"https://t.me/{SUPPORT_USERNAME}"
                )
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
        ]
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    if is_subscription_active(user_id):
        user = get_user(user_id)
        try:
            until = datetime.datetime.fromisoformat(user[3])
            remaining = (until - datetime.datetime.now()).days
        except (ValueError, TypeError):
            remaining = 0
        tariff = user[2] or "не выбран"
        max_dev = user[8] or 3
        text = (
            f"✅ **Подписка активна**\n\n"
            f"📦 Тариф: {tariff}\n"
            f"📱 Устройств: {max_dev}\n"
            f"📅 Осталось дней: {remaining}"
        )
        await callback.answer(text, show_alert=True)
    else:
        await callback.answer("❌ Нет активной подписки. Купите за 500 ₽.", show_alert=True)

@dp.callback_query(F.data == "choose_device")
async def choose_device(callback: CallbackQuery):
    if not is_subscription_active(callback.from_user.id):
        await callback.answer("❌ У вас нет активной подписки.", show_alert=True)
        return

    await callback.message.edit_text(
        "Выберите устройство для подключения:",
        reply_markup=device_selection_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("device_"))
async def send_device_connection(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not is_subscription_active(user_id):
        await callback.answer("❌ У вас нет активной подписки.", show_alert=True)
        return

    user = get_user(user_id)
    subscription_url = user[7] if user and len(user) > 7 else None
    
    if not subscription_url:
        await callback.answer("❌ Ошибка: ссылка не найдена. Обратитесь в поддержку.", show_alert=True)
        return

    device_key = callback.data.removeprefix("device_")
    try:
        text = device_connection_text(device_key, subscription_url)
    except ValueError:
        await callback.answer("❌ Неизвестное устройство.", show_alert=True)
        return

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=delivered_connection_keyboard()
    )
    await callback.answer("✅ Инструкция готова")

# =====================================================
# АДМИН-ПАНЕЛЬ
# =====================================================

@dp.callback_query(F.data == "admin")
async def admin_panel(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    text = "🔧 **Админ-панель Delta VPN**\n\nВыберите действие:"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=admin_menu_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        return
    users = get_all_users()
    if not users:
        await callback.answer("👥 Пользователей нет", show_alert=True)
        return
    text = f"👥 **Все пользователи:** {len(users)}\n\nНажмите на пользователя для управления:"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=admin_users_keyboard(users, 0))
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_users_page_"))
async def admin_users_page(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        return
    page = int(callback.data.replace("admin_users_page_", ""))
    users = get_all_users()
    if users:
        text = f"👥 **Все пользователи:** {len(users)}\n\nНажмите на пользователя для управления:"
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=admin_users_keyboard(users, page))
    await callback.answer()

@dp.callback_query(F.data == "admin_paid")
async def admin_paid(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        return
    
    users = get_paid_users()
    if not users:
        await callback.message.edit_text(
            "💰 **Платные пользователи:** 0\n\nПока нет платных пользователей.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]
                ]
            )
        )
        await callback.answer()
        return
    
    text = f"💰 **Платные пользователи:** {len(users)}\n\nНажмите на пользователя для управления:"
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=admin_paid_keyboard(users, 0)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_paid_page_"))
async def admin_paid_page(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        return
    page = int(callback.data.replace("admin_paid_page_", ""))
    users = get_paid_users()
    if users:
        text = f"💰 **Платные пользователи:** {len(users)}\n\nНажмите на пользователя для управления:"
        await callback.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=admin_paid_keyboard(users, page)
        )
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_user_"))
async def admin_user_detail(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        return
    target_id = int(callback.data.replace("admin_user_", ""))
    user = get_user(target_id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    username = user[1] or "нет"
    tariff = user[2] or "нет"
    until = user[3] or "нет"
    paid = "✅" if user[4] else "❌"
    manual = "✅" if user[5] else "❌"
    privacy = "✅" if user[6] else "❌"
    sub_hash = user[7] or "нет"
    max_dev = user[8] or 3
    
    # Проверяем, является ли until датой
    try:
        if until and until != "нет" and until is not None:
            until_date = datetime.datetime.fromisoformat(until)
            if until_date > datetime.datetime.now():
                remaining = (until_date - datetime.datetime.now()).days
                status_text = f"✅ Активна (осталось {remaining} дн.)"
            else:
                status_text = "❌ Истекла"
        else:
            status_text = "❌ Нет подписки"
    except (ValueError, TypeError):
        status_text = "❌ Некорректная дата"
        until = "ошибка в данных"
    
    text = (
        f"👤 **Информация о пользователе**\n\n"
        f"🆔 ID: {target_id}\n"
        f"👤 Username: @{username}\n"
        f"📦 Тариф: {tariff}\n"
        f"📱 Устройств: {max_dev}\n"
        f"🔗 Хеш: {sub_hash}\n"
        f"📅 До: {until}\n"
        f"📊 Статус: {status_text}\n"
        f"💳 Оплачено: {paid}\n"
        f"✋ Выдано вручную: {manual}\n"
        f"🔒 Условия приняты: {privacy}\n\n"
        "Выберите действие:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Выдать подписку",
                    callback_data=f"admin_grant_{target_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отозвать",
                    callback_data=f"admin_revoke_{target_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Сбросить устройства",
                    callback_data=f"admin_reset_{target_id}",
                ),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users")],
        ]
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "admin_active")
async def admin_active(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        return
    subs = get_active_subscriptions()
    if not subs:
        text = "📊 **Активных подписок:** 0"
    else:
        text = f"📊 **Активных подписок:** {len(subs)}\n\n"
        for sub in subs[:20]:
            uid, username, tariff, until, manual, sub_hash, max_dev = sub
            try:
                until_date = datetime.datetime.fromisoformat(until)
                remaining = (until_date - datetime.datetime.now()).days
            except (ValueError, TypeError):
                remaining = 0
            source = "🔹 Ручная" if manual else "🔹 Авто"
            text += f"👤 {uid} (@{username or 'no_name'}) — {tariff} — {remaining} дн. {source}\n"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]
        ]
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        return
    users = get_all_users()
    active = get_active_subscriptions()
    paid_users = [u for u in users if u[4] == 1]
    manual_users = [u for u in users if u[5] == 1]
    privacy_accepted = [u for u in users if u[6] == 1]
    
    total_revenue = sum([500 if u[2] == "3_devices" else 650 for u in paid_users])
    
    text = (
        "📊 **Статистика Delta VPN:**\n\n"
        f"👥 Всего пользователей: {len(users)}\n"
        f"✅ Активных подписок: {len(active)}\n"
        f"💳 Платных пользователей: {len(paid_users)}\n"
        f"✋ Выдано вручную: {len(manual_users)}\n"
        f"🔒 Приняли условия: {len(privacy_accepted)}\n"
        f"💰 Доход: {total_revenue} ₽"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]
        ]
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "admin_logs")
async def admin_logs(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT admin_id, action, target_id, timestamp FROM admin_logs ORDER BY id DESC LIMIT 20")
    logs = cur.fetchall()
    conn.close()
    
    if not logs:
        text = "📋 **Логи:** Пусто"
    else:
        text = "📋 **Последние логи:**\n\n"
        for log in logs:
            admin_id, action, target, ts = log
            text += f"🕐 {ts[:16]} | Админ {admin_id} | {action} | ID {target}\n"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]
        ]
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "admin_grant")
async def admin_grant(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        return
    await callback.message.answer(
        "➕ **Введите ID пользователя и тариф:**\n\n"
        "Пример: `123456789 3`\n"
        "• 3 устройства — введите `3`\n"
        "• 5 устройств — введите `5`"
    )
    await state.set_state(AdminStates.awaiting_grant_id)
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_grant_"))
async def admin_grant_quick(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        return
    target_id = int(callback.data.replace("admin_grant_", ""))
    
    tariff_key = "3_devices"
    max_devices = 3
    
    try:
        result = await create_subscription(max_devices, f"user_{target_id}")
        subscription_hash = result.get("hash")
        subscription_url = result.get("subscription_url")
        
        if subscription_hash and subscription_url:
            set_subscription(target_id, tariff_key, subscription_hash, max_devices, "manual")
            log_admin_action(user_id, "grant_subscription", target_id)
            
            await callback.answer(f"✅ Подписка выдана пользователю {target_id}", show_alert=True)
            
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users")]
                ]
            )
            await callback.message.edit_text(
                f"✅ Подписка успешно выдана пользователю {target_id}!",
                reply_markup=kb
            )
            
            try:
                text = (
                    "🎉 **Вам была выдана подписка Delta VPN навсегда!**\n\n"
                    f"📦 Тариф: {TARIFFS[tariff_key]['name']}\n"
                    f"📱 Устройств: {max_devices}\n\n"
                    "Выберите устройство для подключения:"
                )
                await bot.send_message(
                    target_id,
                    text,
                    parse_mode="Markdown",
                    reply_markup=device_selection_keyboard()
                )
            except:
                pass
        else:
            await callback.answer("❌ Ошибка создания подписки", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("admin_reset_"))
async def admin_reset_devices(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        return
    
    target_id = int(callback.data.replace("admin_reset_", ""))
    user = get_user(target_id)
    
    if not user or not user[7]:
        await callback.answer("❌ У пользователя нет активной подписки", show_alert=True)
        return
    
    try:
        result = await reset_devices(user[7])
        if result.get("ok"):
            log_admin_action(user_id, "reset_devices", target_id)
            await callback.answer(f"✅ Устройства сброшены для {target_id}", show_alert=True)
        else:
            await callback.answer(f"❌ Ошибка: {result.get('error')}", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@dp.callback_query(F.data == "admin_revoke")
async def admin_revoke(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        return
    await callback.message.answer("❌ **Введите ID пользователя для отзыва подписки:**\n\nПример: `123456789`")
    await state.set_state(AdminStates.awaiting_revoke_id)
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_revoke_"))
async def admin_revoke_quick(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    if user_id not in ADMIN_IDS:
        return
    target_id = int(callback.data.replace("admin_revoke_", ""))
    revoke_subscription(target_id)
    log_admin_action(user_id, "revoke_subscription", target_id)
    await callback.answer(f"❌ Подписка отозвана у {target_id}", show_alert=True)
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users")]
        ]
    )
    await callback.message.edit_text(
        f"❌ Подписка отозвана у пользователя {target_id}.",
        reply_markup=kb
    )
    try:
        await bot.send_message(target_id, "❌ Ваша подписка Delta VPN была отозвана администратором.")
    except:
        pass

# =====================================================
# ОБРАБОТКА СООБЩЕНИЙ ДЛЯ АДМИН-ДЕЙСТВИЙ (FSM)
# =====================================================

@dp.message(AdminStates.awaiting_grant_id)
async def process_grant_id(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    
    try:
        parts = message.text.strip().split()
        target_id = int(parts[0])
        tariff_choice = parts[1] if len(parts) > 1 else "3"
        
        if tariff_choice == "5":
            tariff_key = "5_devices"
            max_devices = 5
        else:
            tariff_key = "3_devices"
            max_devices = 3
        
        user = get_user(target_id)
        if not user:
            await message.answer("❌ Пользователь с таким ID не найден.")
            return
        
        result = await create_subscription(max_devices, f"user_{target_id}")
        subscription_hash = result.get("hash")
        subscription_url = result.get("subscription_url")
        
        if subscription_hash and subscription_url:
            set_subscription(target_id, tariff_key, subscription_hash, max_devices, "manual")
            log_admin_action(user_id, "grant_subscription", target_id)
            await message.answer(f"✅ Подписка выдана пользователю {target_id}!")
            
            try:
                text = (
                    "🎉 **Вам была выдана подписка Delta VPN навсегда!**\n\n"
                    f"📦 Тариф: {TARIFFS[tariff_key]['name']}\n"
                    f"📱 Устройств: {max_devices}\n\n"
                    "Выберите устройство для подключения:"
                )
                await bot.send_message(
                    target_id,
                    text,
                    parse_mode="Markdown",
                    reply_markup=device_selection_keyboard()
                )
            except:
                pass
        else:
            await message.answer("❌ Ошибка создания подписки")
            
    except ValueError:
        await message.answer("❌ Некорректный ID. Введите число.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    await state.clear()

@dp.message(AdminStates.awaiting_revoke_id)
async def process_revoke_id(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    try:
        target_id = int(message.text.strip())
        revoke_subscription(target_id)
        log_admin_action(user_id, "revoke_subscription", target_id)
        await message.answer(f"❌ Подписка отозвана у пользователя {target_id}!")
        try:
            await bot.send_message(target_id, "❌ Ваша подписка Delta VPN была отозвана администратором.")
        except:
            pass
    except ValueError:
        await message.answer("❌ Некорректный ID. Введите число.")
    await state.clear()

# =====================================================
# ЗАПУСК
# =====================================================

async def main():
    logging.basicConfig(level=logging.INFO)
    token = require_config("BOT_TOKEN", BOT_TOKEN)
    init_db()
    fix_invalid_dates()  # Исправляем некорректные даты
    print("🚀 Бот Delta VPN запущен!")
    print(f"👤 Администраторы: {ADMIN_IDS}")
    print(f"💰 Тарифы: 3 устройства — 500 ₽, 5 устройств — 650 ₽")
    print(f"🔗 Worker API: {WORKER_API_URL}")
    print(f"📱 Поддержка: @{SUPPORT_USERNAME}")
    async with Bot(token=token) as bot:
        await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ConfigurationError as error:
        logging.error("%s", error)
        raise SystemExit(1) from error