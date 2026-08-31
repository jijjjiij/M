#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import sqlite3
import datetime
import time
import logging
import json
import aiohttp
from typing import Optional, Tuple, List
import sys

try:
    from config import *
except ImportError:
    print("❌ config.py не найден!")
    sys.exit(1)

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import requests

# =====================================================
# ГЛОБАЛЬНЫЕ СЛОВАРИ
# =====================================================
user_links = {}
user_hashes = {}
admin_reply_targets = {}

# =====================================================
# БАЗА ДАННЫХ
# =====================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
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
            "INSERT INTO users (user_id, username, privacy_accepted) VALUES (?, ?, 0)",
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
    if user and len(user) > 2:
        return user[2] == 1
    return False

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
    cur.execute("SELECT user_id, username, privacy_accepted FROM users ORDER BY user_id")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_all_user_ids() -> List[int]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]

# =====================================================
# API ВОРКЕРА
# =====================================================
async def create_subscription(max_devices: int, days: int, note: str = "") -> dict:
    url = f"{WORKER_API_URL}/api/create"
    headers = {"Content-Type": "application/json"}
    expire_date = (datetime.datetime.now() + datetime.timedelta(days=days)).isoformat()
    data = {"max_devices": max_devices, "note": note, "expire_date": expire_date}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            if response.status == 200:
                result = await response.json()
                if result.get("ok"):
                    return result
                raise Exception(f"API error: {result.get('error', 'Unknown error')}")
            error_text = await response.text()
            raise Exception(f"API error {response.status}: {error_text}")

async def create_test_subscription(max_devices: int, hours: int, note: str = "") -> dict:
    url = f"{WORKER_API_URL}/api/create"
    headers = {"Content-Type": "application/json"}
    expire_date = (datetime.datetime.now() + datetime.timedelta(hours=hours)).isoformat()
    data = {"max_devices": max_devices, "note": note, "expire_date": expire_date}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            if response.status == 200:
                result = await response.json()
                if result.get("ok"):
                    return result
                raise Exception(f"API error: {result.get('error', 'Unknown error')}")
            error_text = await response.text()
            raise Exception(f"API error {response.status}: {error_text}")

async def get_subscription_info(hash_id: str) -> dict:
    url = f"{WORKER_API_URL}/api/info/{hash_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            raise Exception(f"API error {response.status}")

async def reset_devices(hash_id: str) -> dict:
    url = f"{WORKER_API_URL}/api/reset/{hash_id}"
    async with aiohttp.ClientSession() as session:
        async with session.delete(url) as response:
            if response.status == 200:
                return await response.json()
            raise Exception(f"API error {response.status}")

async def delete_device(hash_id: str, hwid: str) -> dict:
    url = f"{WORKER_API_URL}/api/device/{hash_id}/{hwid}"
    async with aiohttp.ClientSession() as session:
        async with session.delete(url) as response:
            if response.status == 200:
                return await response.json()
            raise Exception(f"API error {response.status}")

async def delete_subscription(hash_id: str) -> dict:
    url = f"{WORKER_API_URL}/api/sub/{hash_id}"
    async with aiohttp.ClientSession() as session:
        async with session.delete(url) as response:
            if response.status == 200:
                return await response.json()
            raise Exception(f"API error {response.status}")

def get_tariff_by_devices(max_devices: int, days: int) -> str:
    if max_devices == 3:
        return "3_devices_1m" if days == 30 else "3_devices_3m"
    elif max_devices == 5:
        return "5_devices_1m" if days == 30 else "5_devices_3m"
    return "3_devices_1m"

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
    headers = {"Authorization": f"Bearer {PLATEGA_API_KEY}", "Content-Type": "application/json"}
    response = requests.post(f"{PLATEGA_API_URL}/payments", json=payload, headers=headers, timeout=30)
    if 200 <= response.status_code < 300:
        data = response.json()
        return {"payment_url": data.get("payment_url"), "order_id": order_id}
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
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN, "Content-Type": "application/json"}
    response = requests.post("https://pay.crypt.bot/api/createInvoice", json=payload, headers=headers, timeout=30)
    if response.status_code == 200:
        data = response.json()
        if data.get("ok"):
            invoice = data["result"]
            save_payment(user_id, order_id, amount_rub, tariff, "pending_crypto")
            return {"payment_url": invoice.get("pay_url"), "order_id": order_id, "invoice_id": invoice.get("invoice_id")}
        raise Exception(f"CryptoBot ошибка: {data}")
    raise Exception(f"CryptoBot ошибка: {response.status_code} - {response.text}")

def check_crypto_payment(invoice_id: int) -> str:
    require_config("CRYPTO_BOT_TOKEN", CRYPTO_BOT_TOKEN)
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    params = {"invoice_ids": invoice_id}
    response = requests.get("https://pay.crypt.bot/api/getInvoices", params=params, headers=headers, timeout=30)
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
    response = requests.get(f"{PLATEGA_API_URL}/payments/{order_id}", headers=headers, timeout=30)
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
    awaiting_broadcast_text = State()
    awaiting_test_user = State()

class PrivacyStates(StatesGroup):
    waiting_acceptance = State()

# =====================================================
# КЛАВИАТУРЫ
# =====================================================
def privacy_accept_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Политика конфиденциальности", url=PRIVACY_POLICY_URL)],
            [InlineKeyboardButton(text="📋 Пользовательское соглашение", url=TERMS_URL)],
            [InlineKeyboardButton(text="✅ Согласиться", callback_data="accept_privacy")],
        ]
    )

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Купить доступ", callback_data="buy")],
            [InlineKeyboardButton(text="📱 Моя подписка", callback_data="my_subscription")],
            [InlineKeyboardButton(text="📊 Статус подписки", callback_data="subscription_status")],
            [InlineKeyboardButton(text="🗑️ Удалить подписку", callback_data="delete_my_subscription")],
            [InlineKeyboardButton(text="ℹ️ О Delta", callback_data="about")],
            [InlineKeyboardButton(text="📄 Документы", callback_data="documents")],
            [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
        ]
    )

def tariffs_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔥 3 устройства (1 мес) — 240 ₽", callback_data="tariff_3_devices_1m")],
            [InlineKeyboardButton(text="🚀 5 устройств (1 мес) — 380 ₽", callback_data="tariff_5_devices_1m")],
            [InlineKeyboardButton(text="🔥 3 устройства (3 мес) — 650 ₽", callback_data="tariff_3_devices_3m")],
            [InlineKeyboardButton(text="🚀 5 устройств (3 мес) — 1000 ₽", callback_data="tariff_5_devices_3m")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")],
        ]
    )

def payment_methods_keyboard(tariff: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Карта / СБП", callback_data=f"pay_card_{tariff}"),
             InlineKeyboardButton(text="🪙 Крипто (USDT)", callback_data=f"pay_crypto_{tariff}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="buy")],
        ]
    )

def documents_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Политика конфиденциальности", callback_data="show_privacy")],
            [InlineKeyboardButton(text="📋 Пользовательское соглашение", callback_data="show_terms")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")],
        ]
    )

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Все пользователи", callback_data="admin_users")],
            [InlineKeyboardButton(text="➕ Выдать подписку", callback_data="admin_grant")],
            [InlineKeyboardButton(text="🧪 Тестовая подписка", callback_data="admin_test")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
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
        user_id, username, _ = user
        rows.append([InlineKeyboardButton(text=f"👤 {user_id} (@{username or 'no_name'})", callback_data=f"admin_user_{user_id}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_users_page_{page-1}"))
    if end < len(users):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"admin_users_page_{page+1}"))
    if nav_buttons:
        rows.append(nav_buttons)
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def device_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💻 Windows", callback_data="device_windows")],
            [InlineKeyboardButton(text="🍎 iPhone", callback_data="device_iphone")],
            [InlineKeyboardButton(text="🤖 Android", callback_data="device_android")],
            [InlineKeyboardButton(text="🖥 macOS", callback_data="device_macos")],
            [InlineKeyboardButton(text="🐧 Linux", callback_data="device_linux")],
            [InlineKeyboardButton(text="📺 TV", callback_data="device_tv")],
        ]
    )

def delivered_connection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Моя подписка", callback_data="my_subscription")],
            [InlineKeyboardButton(text="📊 Статус подписки", callback_data="subscription_status")],
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
        "После добавления ссылки включите соединение в HAPP.\n\n"
        "📌 Имя устройства будет определено автоматически при первом подключении."
    )

# =====================================================
# БОТ
# =====================================================
dp = Dispatcher(storage=MemoryStorage())

def format_expire_date(expire_date_str: str) -> str:
    if not expire_date_str:
        return "не указана"
    try:
        expire_date = datetime.datetime.fromisoformat(expire_date_str)
        now = datetime.datetime.now()
        if expire_date < now:
            return "❌ Истекла"
        days = (expire_date - now).days
        hours = (expire_date - now).seconds // 3600
        return f"✅ {days} дн. {hours} ч." if days > 0 else f"✅ {hours} ч."
    except:
        return "ошибка"

# =====================================================
# ГЛАВНОЕ МЕНЮ
# =====================================================
async def show_main_menu(message: Message, user_id: int):
    hash_id = user_hashes.get(user_id)
    if not hash_id:
        await show_main_menu_without_sub(message)
        return
    try:
        info = await get_subscription_info(hash_id)
        if not info.get("ok"):
            await show_main_menu_without_sub(message)
            return
        max_devices = info.get("max_devices", 3)
        used = info.get("used", 0)
        expire_date = info.get("expire_date")
        is_expired = info.get("is_expired", True)
        
        tariff_name = None
        for key, tariff in TARIFFS.items():
            if tariff["max_devices"] == max_devices:
                tariff_name = tariff["name"]
                break
        if not tariff_name:
            tariff_name = f"{max_devices} устройства"
        
        if is_expired:
            await message.answer(
                f"⚠️ **ВАША ПОДПИСКА ЗАКОНЧИЛАСЬ**\n\n"
                f"📦 Тариф: {tariff_name}\n"
                f"📅 Срок: истек\n\n"
                "Купите новую подписку.",
                parse_mode="Markdown", reply_markup=main_menu_keyboard()
            )
        else:
            await message.answer(
                f"🚀 **Delta VPN**\n\n"
                f"📦 Тариф: {tariff_name}\n"
                f"📱 Устройств: {used}/{max_devices}\n"
                f"📅 Осталось: {format_expire_date(expire_date)}\n\n"
                "Выберите действие:",
                parse_mode="Markdown", reply_markup=main_menu_keyboard()
            )
    except Exception as e:
        print(f"Ошибка статуса: {e}")
        await show_main_menu_without_sub(message)

async def show_main_menu_without_sub(message: Message):
    await message.answer(
        "🚀 **Delta VPN**\n\nДобро пожаловать! Выберите тариф:\n\n"
        "🔥 **3 устройства (1 мес)** — 240 ₽\n"
        "🚀 **5 устройств (1 мес)** — 380 ₽\n"
        "🔥 **3 устройства (3 мес)** — 650 ₽\n"
        "🚀 **5 устройств (3 мес)** — 1000 ₽\n\n"
        "💳 Оплата: карта, СБП, криптовалюта\n📱 Работает через HAPP",
        parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )

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
        await message.answer(
            "🔒 **Для использования Delta VPN необходимо принять условия**\n\nОзнакомьтесь с документами и нажмите «Согласиться»:",
            parse_mode="Markdown", reply_markup=privacy_accept_keyboard()
        )
        return
    await show_main_menu(message, user_id)

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа.")
        return
    await message.answer("🔧 **Админ-панель**", parse_mode="Markdown", reply_markup=admin_menu_keyboard())

# =====================================================
# ОСНОВНЫЕ КОЛБЭКИ
# =====================================================
@dp.callback_query(F.data == "accept_privacy", PrivacyStates.waiting_acceptance)
async def accept_privacy(callback: CallbackQuery, state: FSMContext):
    set_privacy_accepted(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text("✅ Условия приняты!", parse_mode="Markdown")
    await show_main_menu(callback.message, callback.from_user.id)
    await callback.answer()

@dp.callback_query(F.data == "back")
async def back_to_main(callback: CallbackQuery):
    await show_main_menu(callback.message, callback.from_user.id)
    await callback.answer()

@dp.callback_query(F.data == "buy")
async def buy_subscription(callback: CallbackQuery):
    await callback.message.edit_text("🚀 **Выберите тариф:**", parse_mode="Markdown", reply_markup=tariffs_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("tariff_"))
async def select_tariff(callback: CallbackQuery):
    tariff_key = callback.data.replace("tariff_", "")
    if tariff_key not in TARIFFS:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return
    tariff = TARIFFS[tariff_key]
    text = (
        f"💰 **Вы выбрали: {tariff['name']}**\n\n"
        f"💰 Стоимость: **{tariff['price']} ₽**\n"
        f"📱 Устройств: {tariff['max_devices']}\n"
        f"📅 Срок: {tariff['days']} дней\n\n"
        f"{tariff['description']}\n\n"
        "Выберите способ оплаты:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=payment_methods_keyboard(tariff_key))
    await callback.answer()

# =====================================================
# МОЯ ПОДПИСКА
# =====================================================
@dp.callback_query(F.data == "my_subscription")
async def my_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    hash_id = user_hashes.get(user_id)
    if not hash_id:
        await callback.answer("❌ У вас нет активной подписки", show_alert=True)
        return
    try:
        info = await get_subscription_info(hash_id)
        if not info.get("ok") or info.get("is_expired"):
            await callback.answer("⚠️ Подписка неактивна или истекла", show_alert=True)
            return
        devices = info.get("devices", [])
        if not devices:
            await callback.answer("📱 У вас нет подключенных устройств", show_alert=True)
            return
        text = f"📱 **Мои устройства ({len(devices)}/{info.get('max_devices',3)})**\n\n"
        kb_buttons = []
        for i, dev in enumerate(devices, 1):
            hwid = dev.get("hwid", "неизвестно")
            device_name = dev.get("device_name", f"Устройство {i}")
            first_seen = dev.get("first_seen", "").split("T")[0] if dev.get("first_seen") else "неизвестно"
            text += f"{i}. **{device_name}**\n   🆔 `{hwid[:12]}...`\n   📅 с {first_seen}\n\n"
            kb_buttons.append([InlineKeyboardButton(
                text=f"❌ Удалить {device_name}",
                callback_data=f"delete_device_{hash_id}_{hwid}"
            )])
        kb_buttons.append([InlineKeyboardButton(text="➕ Добавить устройство", callback_data="add_device")])
        kb_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb_buttons))
        await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@dp.callback_query(F.data == "add_device")
async def add_device(callback: CallbackQuery):
    user_id = callback.from_user.id
    hash_id = user_hashes.get(user_id)
    if not hash_id:
        await callback.answer("❌ У вас нет активной подписки", show_alert=True)
        return
    await callback.message.edit_text(
        "📱 **Выберите тип устройства:**\n\nПри первом подключении через HAPP название будет определено автоматически.",
        parse_mode="Markdown", reply_markup=device_selection_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("device_"))
async def send_device_connection(callback: CallbackQuery):
    user_id = callback.from_user.id
    device_key = callback.data.replace("device_", "")
    subscription_url = user_links.get(user_id)
    if not subscription_url:
        await callback.answer("❌ Ссылка не найдена", show_alert=True)
        return
    try:
        text = device_connection_text(device_key, subscription_url)
    except ValueError:
        await callback.answer("❌ Неизвестное устройство.", show_alert=True)
        return
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=delivered_connection_keyboard())
    await callback.answer("✅ Инструкция готова")

# =====================================================
# СТАТУС ПОДПИСКИ
# =====================================================
@dp.callback_query(F.data == "subscription_status")
async def subscription_status(callback: CallbackQuery):
    user_id = callback.from_user.id
    hash_id = user_hashes.get(user_id)
    if not hash_id:
        await callback.answer("❌ У вас нет активной подписки", show_alert=True)
        return
    try:
        info = await get_subscription_info(hash_id)
        if not info.get("ok"):
            await callback.answer("❌ Ошибка получения данных", show_alert=True)
            return
        max_devices = info.get("max_devices", 3)
        used = info.get("used", 0)
        expire_date = info.get("expire_date")
        is_expired = info.get("is_expired", True)
        devices = info.get("devices", [])
        if is_expired:
            text = f"⚠️ **ВАША ПОДПИСКА ЗАКОНЧИЛАСЬ**\n\n📱 Устройств: {used}/{max_devices}\nКупите новую подписку."
        else:
            text = f"📊 **Статус подписки**\n\n📱 Устройств: **{used}/{max_devices}**\n📅 Осталось: **{format_expire_date(expire_date)}**\n"
            if devices:
                text += "\n🖥️ **Подключенные устройства:**\n"
                for i, dev in enumerate(devices, 1):
                    device_name = dev.get("device_name", f"Устройство {i}")
                    hwid = dev.get("hwid", "неизвестно")[:12]
                    first_seen = dev.get("first_seen", "").split("T")[0] if dev.get("first_seen") else "неизвестно"
                    text += f"{i}. **{device_name}** (`{hwid}...`, с {first_seen})\n"
            else:
                text += "\n📱 Нет подключенных устройств"
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
        await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

# =====================================================
# УДАЛЕНИЕ УСТРОЙСТВА
# =====================================================
@dp.callback_query(F.data.startswith("delete_device_"))
async def delete_device_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.replace("delete_device_", "").split("_", 1)
    
    if len(parts) < 2:
        await callback.answer("❌ Ошибка формата", show_alert=True)
        return
    
    hash_id = parts[0]
    hwid = parts[1]
    
    try:
        result = await delete_device(hash_id, hwid)
        if result.get("ok"):
            await callback.answer("✅ Устройство удалено!", show_alert=True)
            await my_subscription(callback)
        else:
            await callback.answer(f"❌ Ошибка: {result.get('error')}", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

# =====================================================
# УДАЛЕНИЕ ПОДПИСКИ ПОЛЬЗОВАТЕЛЕМ
# =====================================================
@dp.callback_query(F.data == "delete_my_subscription")
async def delete_my_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    hash_id = user_hashes.get(user_id)
    if not hash_id:
        await callback.answer("❌ У вас нет активной подписки", show_alert=True)
        return
    try:
        info = await get_subscription_info(hash_id)
        if not info.get("ok") or info.get("is_expired"):
            await callback.answer("⚠️ Подписка неактивна", show_alert=True)
            return
    except:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_sub_{hash_id}"),
             InlineKeyboardButton(text="❌ Отмена", callback_data="back")]
        ]
    )
    await callback.message.edit_text(
        "⚠️ **Вы действительно хотите удалить свою подписку?**\n\nЭто действие удалит все устройства и доступ.",
        parse_mode="Markdown", reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_delete_sub_"))
async def confirm_delete_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    hash_id = callback.data.replace("confirm_delete_sub_", "")
    try:
        await delete_subscription(hash_id)
        user_links.pop(user_id, None)
        user_hashes.pop(user_id, None)
        await callback.message.edit_text(
            "🗑️ **Ваша подписка удалена**\n\nВы можете купить новую в любой момент.",
            parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )
        await callback.answer("✅ Подписка удалена")
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

# =====================================================
# ТЕСТОВАЯ ПОДПИСКА (АДМИН)
# =====================================================

@dp.callback_query(F.data == "admin_test")
async def admin_test_subscription(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 3 устройства", callback_data="test_3")],
            [InlineKeyboardButton(text="📱 5 устройств", callback_data="test_5")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin")],
        ]
    )
    
    await callback.message.edit_text(
        "🧪 **Тестовая подписка**\n\n"
        "Выберите количество устройств:\n"
        "⏱️ Срок: **1 час**\n"
        "💰 Стоимость: **бесплатно**\n\n"
        "После выбора введите ID пользователя.",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("test_"))
async def test_select_devices(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    max_devices = int(callback.data.replace("test_", ""))
    await state.update_data(test_max_devices=max_devices)
    
    await callback.message.edit_text(
        f"🧪 **Тестовая подписка ({max_devices} устройства)**\n\n"
        "Введите ID пользователя (Telegram ID):\n"
        "Пример: `123456789`",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.awaiting_test_user)
    await callback.answer()

@dp.message(AdminStates.awaiting_test_user)
async def process_test_user(message: Message, state: FSMContext, bot: Bot):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS:
        return
    
    try:
        target_id = int(message.text.strip())
        user = get_user(target_id)
        if not user:
            await message.answer("❌ Пользователь с таким ID не найден.")
            return
        
        data = await state.get_data()
        max_devices = data.get("test_max_devices", 3)
        
        result = await create_test_subscription(max_devices, 1, f"test_user_{target_id}")
        subscription_url = result.get("subscription_url")
        hash_id = result.get("hash")
        
        if subscription_url and hash_id:
            user_links[target_id] = subscription_url
            user_hashes[target_id] = hash_id
            
            log_admin_action(admin_id, f"test_subscription_{max_devices}d_1h", target_id)
            
            await message.answer(
                f"✅ **Тестовая подписка создана!**\n\n"
                f"👤 Пользователь: {target_id}\n"
                f"📱 Устройств: {max_devices}\n"
                f"⏱️ Срок: 1 час\n"
                f"🔗 Ссылка: `{subscription_url}`",
                parse_mode="Markdown"
            )
            
            try:
                await bot.send_message(
                    target_id,
                    f"🧪 **Тестовая подписка Delta VPN!**\n\n"
                    f"📱 {max_devices} устройств\n"
                    f"⏱️ Действует 1 час\n"
                    f"🔗 Ваша ссылка:\n`{subscription_url}`\n\n"
                    "Выберите устройство:",
                    parse_mode="Markdown",
                    reply_markup=device_selection_keyboard()
                )
            except Exception as e:
                await message.answer(f"⚠️ Не удалось отправить пользователю: {e}")
        else:
            await message.answer("❌ Ошибка создания тестовой подписки")
            
    except ValueError:
        await message.answer("❌ Некорректный ID. Введите число.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    
    await state.clear()
    await show_main_menu(message, admin_id)

# =====================================================
# ОСТАЛЬНЫЕ КОЛБЭКИ
# =====================================================
@dp.callback_query(F.data == "documents")
async def show_documents_menu(callback: CallbackQuery):
    await callback.message.edit_text("📚 **Документы**", parse_mode="Markdown", reply_markup=documents_menu_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "show_privacy")
async def show_privacy(callback: CallbackQuery):
    await callback.message.edit_text(f"📄 **Политика конфиденциальности**\n\n🔗 {PRIVACY_POLICY_URL}", parse_mode="Markdown", disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="documents")]]))
    await callback.answer()

@dp.callback_query(F.data == "show_terms")
async def show_terms(callback: CallbackQuery):
    await callback.message.edit_text(f"📋 **Пользовательское соглашение**\n\n🔗 {TERMS_URL}", parse_mode="Markdown", disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="documents")]]))
    await callback.answer()

@dp.callback_query(F.data == "about")
async def about_delta(callback: CallbackQuery):
    await callback.message.edit_text("🚀 **О Delta VPN**\n\nОбходит ограничения, увеличивает скорость, безопасное соединение.\n\n🔒 Без логов, серверы в 10 странах.\n📱 Работает с HAPP: https://happ.info/", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]))
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support_delta(callback: CallbackQuery):
    await callback.message.edit_text(f"🆘 **Поддержка**\n\n📱 [@{SUPPORT_USERNAME}](https://t.me/{SUPPORT_USERNAME})\n📧 {SUPPORT_EMAIL}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📩 Написать", url=f"https://t.me/{SUPPORT_USERNAME}")], [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]))
    await callback.answer()

# =====================================================
# ПЛАТЕЖИ
# =====================================================
@dp.callback_query(F.data.startswith("pay_card_"))
async def pay_card(callback: CallbackQuery):
    tariff_key = callback.data.replace("pay_card_", "")
    user_id = callback.from_user.id
    tariff = TARIFFS[tariff_key]
    try:
        create_user(user_id, callback.from_user.username or "unknown")
        result = await asyncio.to_thread(create_platega_payment, tariff["price"], user_id, tariff_key)
        payment_url = result.get("payment_url")
        order_id = result.get("order_id")
        if not payment_url or not order_id:
            raise RuntimeError("Platega не вернул ссылку")
        save_payment(user_id, order_id, tariff["price"], tariff_key, "pending")
        text = f"💳 **Оплата картой / СБП**\n\n📦 {tariff['name']}\n💰 {tariff['price']} ₽\n\n🔗 [Перейти к оплате]({payment_url})"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_payment_{order_id}_{tariff_key}")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="buy")],
            ]
        )
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}")
    await callback.answer()

@dp.callback_query(F.data.startswith("pay_crypto_"))
async def pay_crypto(callback: CallbackQuery):
    tariff_key = callback.data.replace("pay_crypto_", "")
    user_id = callback.from_user.id
    tariff = TARIFFS[tariff_key]
    try:
        create_user(user_id, callback.from_user.username or "unknown")
        result = await asyncio.to_thread(create_crypto_payment, tariff["price"], user_id, tariff_key)
        payment_url = result.get("payment_url")
        invoice_id = result.get("invoice_id")
        if not payment_url or not invoice_id:
            raise RuntimeError("CryptoBot не вернул ссылку")
        text = f"🪙 **Оплата криптовалютой (USDT)**\n\n📦 {tariff['name']}\n💰 ~{round(tariff['price']/100, 2)} USDT\n\n🔗 [Перейти к оплате]({payment_url})"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_crypto_{invoice_id}_{tariff_key}")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="buy")],
            ]
        )
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}")
    await callback.answer()

@dp.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.replace("check_payment_", "").split("_")
    order_id = parts[0]
    tariff_key = parts[1] if len(parts) > 1 else "3_devices_1m"
    try:
        status = await asyncio.to_thread(check_platega_payment, order_id)
        update_payment_status(order_id, status)
        if status == "paid":
            tariff = TARIFFS[tariff_key]
            max_devices = tariff["max_devices"]
            days = tariff["days"]
            result = await create_subscription(max_devices, days, f"user_{user_id}")
            subscription_url = result.get("subscription_url")
            hash_id = result.get("hash")
            if subscription_url and hash_id:
                user_links[user_id] = subscription_url
                user_hashes[user_id] = hash_id
                text = f"✅ **Оплата подтверждена!**\n\nПодписка **{tariff['name']}** активирована.\n\nВыберите устройство:"
                await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=device_selection_keyboard())
                await callback.answer("✅ Подписка активирована!")
            else:
                await callback.answer("❌ Ошибка создания подписки", show_alert=True)
        elif status == "pending":
            await callback.answer("⏳ Платеж обрабатывается. Подождите 1-2 минуты.", show_alert=True)
        else:
            await callback.answer(f"❌ Платеж не прошел. Статус: {status}", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("check_crypto_"))
async def check_crypto(callback: CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.replace("check_crypto_", "").split("_")
    invoice_id = int(parts[0])
    tariff_key = parts[1] if len(parts) > 1 else "3_devices_1m"
    try:
        status = await asyncio.to_thread(check_crypto_payment, invoice_id)
        if status == "paid":
            tariff = TARIFFS[tariff_key]
            max_devices = tariff["max_devices"]
            days = tariff["days"]
            result = await create_subscription(max_devices, days, f"user_{user_id}")
            subscription_url = result.get("subscription_url")
            hash_id = result.get("hash")
            if subscription_url and hash_id:
                user_links[user_id] = subscription_url
                user_hashes[user_id] = hash_id
                text = f"✅ **Оплата криптовалютой подтверждена!**\n\nПодписка **{tariff['name']}** активирована.\n\nВыберите устройство:"
                await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=device_selection_keyboard())
                await callback.answer("✅ Подписка активирована!")
            else:
                await callback.answer("❌ Ошибка создания подписки", show_alert=True)
        elif status == "pending":
            await callback.answer("⏳ Платеж обрабатывается. Проверьте через 5-10 минут.", show_alert=True)
        else:
            await callback.answer("❌ Платеж не прошел или истек.", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

# =====================================================
# РАССЫЛКА
# =====================================================
@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Всем пользователям", callback_data="broadcast_all")],
            [InlineKeyboardButton(text="👤 Конкретному пользователю", callback_data="broadcast_user")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin")],
        ]
    )
    await callback.message.edit_text("📢 **Рассылка**\n\nВыберите тип:", parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "broadcast_all")
async def broadcast_all(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await state.update_data(broadcast_target="all")
    await callback.message.edit_text("📢 **Введите текст сообщения для ВСЕХ пользователей:**", parse_mode="Markdown")
    await state.set_state(AdminStates.awaiting_broadcast_text)
    await callback.answer()

@dp.callback_query(F.data == "broadcast_user")
async def broadcast_user_list(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    users = get_all_users()
    if not users:
        await callback.message.edit_text("❌ Нет пользователей.", parse_mode="Markdown")
        await callback.answer()
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"👤 {u[0]} (@{u[1] or 'no_name'})", callback_data=f"broadcast_user_{u[0]}")] for u in users[:20]
        ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_broadcast")]]
    )
    await callback.message.edit_text(f"👤 **Выберите пользователя:**\nВсего: {len(users)}", parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("broadcast_user_"))
async def broadcast_user_select(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    target_id = int(callback.data.replace("broadcast_user_", ""))
    user = get_user(target_id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    await state.update_data(broadcast_target=target_id)
    await callback.message.edit_text(f"📢 **Введите текст для пользователя {target_id} (@{user[1] or 'no_name'}):**", parse_mode="Markdown")
    await state.set_state(AdminStates.awaiting_broadcast_text)
    await callback.answer()

@dp.message(AdminStates.awaiting_broadcast_text)
async def process_broadcast_text(message: Message, state: FSMContext, bot: Bot):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS:
        return
    data = await state.get_data()
    target = data.get("broadcast_target")
    text = message.text
    if target == "all":
        users = get_all_user_ids()
        sent = 0
        failed = 0
        for uid in users:
            try:
                await bot.send_message(
                    uid,
                    f"📢 **Сообщение от администрации:**\n\n{text}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="✉️ Ответить", callback_data=f"support_reply_{uid}_{admin_id}")]]
                    )
                )
                sent += 1
                await asyncio.sleep(0.05)
            except:
                failed += 1
        log_admin_action(admin_id, "broadcast_all", 0)
        await message.answer(f"✅ **Рассылка завершена!**\n📤 Отправлено: {sent}\n❌ Не доставлено: {failed}")
    else:
        try:
            await bot.send_message(
                target,
                f"📢 **Сообщение от администрации:**\n\n{text}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="✉️ Ответить", callback_data=f"support_reply_{target}_{admin_id}")]]
                )
            )
            log_admin_action(admin_id, "broadcast_user", target)
            await message.answer(f"✅ Сообщение отправлено пользователю {target}")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}")
    await state.clear()
    await show_main_menu(message, admin_id)

# =====================================================
# ОБРАБОТКА ОТВЕТОВ
# =====================================================

@dp.message(F.text)
async def handle_user_message(message: Message, bot: Bot):
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        target = admin_reply_targets.get(user_id)
        if target and not message.text.startswith("/"):
            try:
                await bot.send_message(
                    target,
                    f"📢 **Ответ от поддержки:**\n\n{message.text}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="✉️ Ответить", callback_data=f"support_reply_{target}_{user_id}")]]
                    )
                )
                await message.answer(f"✅ Ответ отправлен пользователю {target}")
                admin_reply_targets.pop(user_id, None)
                log_admin_action(user_id, "reply_to_user", target)
            except Exception as e:
                await message.answer(f"❌ Ошибка: {str(e)}")
        return
    hash_id = user_hashes.get(user_id)
    if not hash_id:
        return
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📩 **Новое сообщение от пользователя**\n\n👤 ID: {user_id}\n👤 @{message.from_user.username or 'не указан'}\n\n📝 {message.text}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="✉️ Ответить", callback_data=f"admin_reply_{admin_id}_{user_id}")]]
                )
            )
        except:
            pass

@dp.callback_query(F.data.startswith("admin_reply_"))
async def admin_reply_callback(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if admin_id not in ADMIN_IDS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    parts = callback.data.replace("admin_reply_", "").split("_")
    
    if len(parts) < 2:
        await callback.answer("❌ Ошибка формата", show_alert=True)
        return
    
    admin_id_from_data = int(parts[0])
    target_id = int(parts[1])
    
    if admin_id != admin_id_from_data:
        await callback.answer("⛔ Это сообщение не для вас", show_alert=True)
        return
    
    admin_reply_targets[admin_id] = target_id
    await callback.message.answer(f"✉️ **Ответ пользователю {target_id}**\n\nНапишите текст ответа:", parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("support_reply_"))
async def support_reply_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.replace("support_reply_", "").split("_")
    
    if len(parts) < 2:
        await callback.answer("❌ Ошибка формата", show_alert=True)
        return
    
    target_user_id = int(parts[0])
    admin_id = int(parts[1])
    
    if user_id != target_user_id:
        await callback.answer("⛔ Это сообщение не для вас", show_alert=True)
        return
    
    await callback.message.answer("✉️ **Напишите ваш ответ:**", parse_mode="Markdown")
    await callback.answer()

# =====================================================
# АДМИН-ПАНЕЛЬ
# =====================================================
@dp.callback_query(F.data == "admin")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("🔧 **Админ-панель**", parse_mode="Markdown", reply_markup=admin_menu_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    users = get_all_users()
    if not users:
        await callback.answer("👥 Пользователей нет", show_alert=True)
        return
    await callback.message.edit_text(f"👥 **Все пользователи:** {len(users)}", parse_mode="Markdown", reply_markup=admin_users_keyboard(users, 0))
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_users_page_"))
async def admin_users_page(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    page = int(callback.data.replace("admin_users_page_", ""))
    users = get_all_users()
    if users:
        await callback.message.edit_text(f"👥 **Все пользователи:** {len(users)}", parse_mode="Markdown", reply_markup=admin_users_keyboard(users, page))
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_user_"))
async def admin_user_detail(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    target_id = int(callback.data.replace("admin_user_", ""))
    user = get_user(target_id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    username = user[1] or "нет"
    privacy = "✅" if user[2] else "❌"
    hash_id = user_hashes.get(target_id)
    sub_info = "Нет подписки"
    if hash_id:
        try:
            info = await get_subscription_info(hash_id)
            if info.get("ok"):
                max_devices = info.get("max_devices", 3)
                used = info.get("used", 0)
                is_expired = info.get("is_expired", True)
                sub_info = "❌ Истекла" if is_expired else f"✅ Активна ({used}/{max_devices})"
        except:
            sub_info = "Ошибка проверки"
    text = f"👤 **Пользователь**\n\n🆔 ID: {target_id}\n👤 @{username}\n🔒 Условия: {privacy}\n📊 Подписка: {sub_info}"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Выдать (3/1мес)", callback_data=f"admin_grant_{target_id}_3_30"),
             InlineKeyboardButton(text="➕ Выдать (5/1мес)", callback_data=f"admin_grant_{target_id}_5_30")],
            [InlineKeyboardButton(text="➕ Выдать (3/3мес)", callback_data=f"admin_grant_{target_id}_3_90"),
             InlineKeyboardButton(text="➕ Выдать (5/3мес)", callback_data=f"admin_grant_{target_id}_5_90")],
            [InlineKeyboardButton(text="🧪 Тест (1 час)", callback_data=f"admin_test_user_{target_id}")],
            [InlineKeyboardButton(text="🔄 Сбросить устройства", callback_data=f"admin_reset_{target_id}")],
            [InlineKeyboardButton(text="❌ Отозвать подписку", callback_data=f"admin_revoke_{target_id}")],
            [InlineKeyboardButton(text="📩 Отправить сообщение", callback_data=f"admin_msg_{target_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users")],
        ]
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_test_user_"))
async def admin_test_user(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    target_id = int(callback.data.replace("admin_test_user_", ""))
    
    try:
        result = await create_test_subscription(3, 1, f"test_user_{target_id}")
        subscription_url = result.get("subscription_url")
        hash_id = result.get("hash")
        
        if subscription_url and hash_id:
            user_links[target_id] = subscription_url
            user_hashes[target_id] = hash_id
            
            log_admin_action(callback.from_user.id, f"test_subscription_3d_1h", target_id)
            
            await callback.answer(f"✅ Тестовая подписка создана для {target_id}", show_alert=True)
            
            await callback.message.edit_text(
                f"✅ **Тестовая подписка создана!**\n\n"
                f"👤 Пользователь: {target_id}\n"
                f"📱 Устройств: 3\n"
                f"⏱️ Срок: 1 час\n"
                f"🔗 Ссылка: `{subscription_url}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users")]]
                )
            )
            
            try:
                await bot.send_message(
                    target_id,
                    f"🧪 **Тестовая подписка Delta VPN!**\n\n"
                    f"📱 3 устройства\n"
                    f"⏱️ Действует 1 час\n"
                    f"🔗 Ваша ссылка:\n`{subscription_url}`\n\n"
                    "Выберите устройство:",
                    parse_mode="Markdown",
                    reply_markup=device_selection_keyboard()
                )
            except Exception as e:
                await callback.message.answer(f"⚠️ Не удалось отправить пользователю: {e}")
        else:
            await callback.answer("❌ Ошибка создания", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("admin_msg_"))
async def admin_msg_user(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    target_id = int(callback.data.replace("admin_msg_", ""))
    await state.update_data(broadcast_target=target_id)
    await callback.message.answer(f"📢 **Введите сообщение для пользователя {target_id}:**")
    await state.set_state(AdminStates.awaiting_broadcast_text)
    await callback.answer()

@dp.callback_query(F.data == "admin_grant")
async def admin_grant(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await callback.message.answer(
        "➕ **Введите ID пользователя и параметры:**\n\nФормат: `ID устройств дней`\nПример: `123456789 3 30`\nДоступные дни: 30, 90",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.awaiting_grant_id)
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_grant_"))
async def admin_grant_quick(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in ADMIN_IDS:
        return
    parts = callback.data.replace("admin_grant_", "").split("_")
    target_id = int(parts[0])
    max_devices = int(parts[1])
    days = int(parts[2])
    try:
        result = await create_subscription(max_devices, days, f"user_{target_id}")
        subscription_url = result.get("subscription_url")
        hash_id = result.get("hash")
        if subscription_url and hash_id:
            user_links[target_id] = subscription_url
            user_hashes[target_id] = hash_id
            log_admin_action(callback.from_user.id, f"grant_{max_devices}_{days}d", target_id)
            await callback.answer(f"✅ Подписка выдана {target_id}", show_alert=True)
            await callback.message.edit_text(f"✅ Подписка создана для {target_id}\n📱 {max_devices} устройств\n📅 {days} дней", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users")]]))
            try:
                await bot.send_message(
                    target_id,
                    f"🎉 **Вам выдана подписка Delta VPN!**\n\n📱 {max_devices} устройств\n📅 {days} дней\n🔗 Ваша ссылка:\n`{subscription_url}`",
                    parse_mode="Markdown",
                    reply_markup=device_selection_keyboard()
                )
            except Exception as e:
                await callback.message.answer(f"⚠️ Не удалось отправить: {e}")
        else:
            await callback.answer("❌ Ошибка", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("admin_reset_"))
async def admin_reset(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    target_id = int(callback.data.replace("admin_reset_", ""))
    hash_id = user_hashes.get(target_id)
    if not hash_id:
        await callback.answer("❌ У пользователя нет подписки", show_alert=True)
        return
    try:
        result = await reset_devices(hash_id)
        if result.get("ok"):
            log_admin_action(callback.from_user.id, "reset_devices", target_id)
            await callback.answer(f"✅ Устройства сброшены для {target_id}", show_alert=True)
        else:
            await callback.answer(f"❌ Ошибка: {result.get('error')}", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("admin_revoke_"))
async def admin_revoke(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in ADMIN_IDS:
        return
    target_id = int(callback.data.replace("admin_revoke_", ""))
    hash_id = user_hashes.get(target_id)
    if not hash_id:
        await callback.answer("❌ У пользователя нет подписки", show_alert=True)
        return
    try:
        await delete_subscription(hash_id)
        user_links.pop(target_id, None)
        user_hashes.pop(target_id, None)
        log_admin_action(callback.from_user.id, "revoke_subscription", target_id)
        await callback.answer(f"✅ Подписка отозвана у {target_id}", show_alert=True)
        await callback.message.edit_text(f"❌ Подписка отозвана у пользователя {target_id}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users")]]))
        try:
            await bot.send_message(target_id, "❌ Ваша подписка Delta VPN была отозвана администратором.")
        except:
            pass
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    users = get_all_users()
    privacy_accepted = [u for u in users if u[2] == 1]
    active_subs = 0
    for uid in user_hashes.keys():
        try:
            info = await get_subscription_info(user_hashes[uid])
            if info.get("ok") and not info.get("is_expired", True):
                active_subs += 1
        except:
            pass
    await callback.message.edit_text(
        f"📊 **Статистика**\n\n👥 Всего: {len(users)}\n✅ Активных: {active_subs}\n🔒 Приняли условия: {len(privacy_accepted)}",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]])
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_logs")
async def admin_logs(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
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
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]]))
    await callback.answer()

# =====================================================
# ОБРАБОТКА FSM (выдача подписки)
# =====================================================
@dp.message(AdminStates.awaiting_grant_id)
async def process_grant_id(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.strip().split()
        if len(parts) < 3:
            await message.answer("❌ Неверный формат. Используйте: `ID устройств дни`")
            return
        target_id = int(parts[0])
        max_devices = int(parts[1])
        days = int(parts[2])
        if max_devices not in [3, 5] or days not in [30, 90]:
            await message.answer("❌ Неверные параметры. Устройства: 3 или 5, дни: 30 или 90.")
            return
        user = get_user(target_id)
        if not user:
            await message.answer("❌ Пользователь не найден.")
            return
        result = await create_subscription(max_devices, days, f"user_{target_id}")
        subscription_url = result.get("subscription_url")
        hash_id = result.get("hash")
        if subscription_url and hash_id:
            user_links[target_id] = subscription_url
            user_hashes[target_id] = hash_id
            log_admin_action(message.from_user.id, f"grant_{max_devices}_{days}d", target_id)
            await message.answer(f"✅ Подписка создана для {target_id} ({max_devices} устройств, {days} дней)")
            try:
                await bot.send_message(
                    target_id,
                    f"🎉 **Вам выдана подписка Delta VPN!**\n\n📱 {max_devices} устройств\n📅 {days} дней\n🔗 Ваша ссылка:\n`{subscription_url}`",
                    parse_mode="Markdown",
                    reply_markup=device_selection_keyboard()
                )
            except Exception as e:
                await message.answer(f"⚠️ Не удалось отправить: {e}")
        else:
            await message.answer("❌ Ошибка создания")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    await state.clear()

# =====================================================
# ЗАПУСК
# =====================================================
async def main():
    logging.basicConfig(level=logging.INFO)
    try:
        token = require_config("BOT_TOKEN", BOT_TOKEN)
    except ConfigurationError as e:
        print(f"❌ {e}")
        print("⚠️ Отредактируйте config.py и укажите BOT_TOKEN")
        return
    init_db()
    print("🚀 Бот Delta VPN запущен!")
    print(f"👤 Администраторы: {ADMIN_IDS}")
    print(f"🔗 Worker API: {WORKER_API_URL}")
    async with Bot(token=token) as bot:
        await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ConfigurationError as error:
        logging.error("%s", error)
        raise SystemExit(1) from error