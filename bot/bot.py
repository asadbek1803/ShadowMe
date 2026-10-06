"""
ShadowMe Telegram Bot (@ShadowMeLoginBot)
=========================================
aiogram 3 + Router arxitekturasi bilan yozilgan.
Barcha Django ORM chaqiruvlari sync_to_async bilan o'ralgan —
chunki aiogram async muhitda ishlaydi.

Jarayon:
    /start yoki /login yoki "OTP Olish" tugmasi
    → Agar yangi foydalanuvchi → telefon so'raydi → TelegramUser yaratadi → OTP yuboradi
    → Agar mavjud foydalanuvchi  → rate limit tekshiradi → OTP yuboradi
"""

import logging
import os
import asyncio
from urllib.parse import quote
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from asgiref.sync import sync_to_async
from django.conf import settings
from accounts.models import TelegramUser, OTPCode

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── FSM holatlari ─────────────────────────────────────────────────────────────

class LoginStates(StatesGroup):
    waiting_for_contact = State()


# ── Routerlar ─────────────────────────────────────────────────────────────────

main_router = Router(name="main")
login_router = Router(name="login")
callback_router = Router(name="callbacks")


# ── sync_to_async wrappers (Django ORM → async) ──────────────────────────────

@sync_to_async
def db_get_user(telegram_id: int):
    """TelegramUser ni topish (None qaytaradi agar yo'q bo'lsa)."""
    try:
        return TelegramUser.objects.get(telegram_id=telegram_id)
    except TelegramUser.DoesNotExist:
        return None


@sync_to_async
def db_get_or_create_user(telegram_id, full_name, username, phone_number, photo_url):
    """TelegramUser yaratish yoki yangilash."""
    user, created = TelegramUser.objects.get_or_create(
        telegram_id=telegram_id,
        defaults={
            "full_name": full_name or "Foydalanuvchi",
            "username": username,
            "phone_number": phone_number,
            "profile_image_url": photo_url,
        },
    )
    if not created:
        update_fields = []
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            update_fields.append("full_name")
        if username and user.username != username:
            user.username = username
            update_fields.append("username")
        if phone_number and user.phone_number != phone_number:
            user.phone_number = phone_number
            update_fields.append("phone_number")
        if photo_url and user.profile_image_url != photo_url:
            user.profile_image_url = photo_url
            update_fields.append("profile_image_url")
        if update_fields:
            user.save(update_fields=update_fields)
    return user, created


@sync_to_async
def db_can_request_otp(user: TelegramUser) -> bool:
    return user.can_request_otp()


@sync_to_async
def db_get_wait_seconds(user: TelegramUser) -> int:
    return user.get_last_otp_wait_seconds()


@sync_to_async
def db_create_otp(user: TelegramUser):
    return OTPCode.create_for_user(user)


@sync_to_async
def db_update_photo(user: TelegramUser, photo_url: str):
    user.profile_image_url = photo_url
    user.save(update_fields=["profile_image_url"])


@sync_to_async
def db_get_active_otp(user: TelegramUser):
    """Foydalanuvchining faol (hali amal qiladigan) OTP sini qaytaradi."""
    return user.get_active_otp()


@sync_to_async
def db_get_active_remaining_seconds(user: TelegramUser) -> int:
    """Faol OTP ning qolgan vaqtini soniyalarda qaytaradi."""
    return user.get_active_otp_remaining_seconds()


# ── Yordamchi funksiyalar ─────────────────────────────────────────────────────

def generate_initials_avatar(full_name: str) -> str:
    """Ism bosh harflaridan avatar URL yaratish (ui-avatars.com)."""
    name = quote(full_name or "U")
    return (
        f"https://ui-avatars.com/api/"
        f"?name={name}"
        f"&background=4F46E5&color=fff"
        f"&size=256&bold=true&format=png"
    )


async def get_user_photo_url(bot: Bot, user_id: int, full_name: str) -> str:
    """
    Foydalanuvchining Telegram profil rasmini olish.
    Rasm bo'lmasa — ismining bosh harflaridan avatar yaratish.
    Har doim URL qaytaradi (None emas).
    """
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            photo = photos.photos[0][-1]
            file = await bot.get_file(photo.file_id)
            return f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
    except Exception as e:
        logger.warning(f"Profil rasmi olinmadi (user_id={user_id}): {e}")

    # Telegram rasmi yo'q — bosh harflardan avatar
    return generate_initials_avatar(full_name)


def contact_keyboard() -> ReplyKeyboardMarkup:
    """Telefon raqamini so'rash uchun tugma."""
    btn = KeyboardButton(text="📱 Telefon raqamimni ulashish", request_contact=True)
    return ReplyKeyboardMarkup(
        keyboard=[[btn]],
        one_time_keyboard=True,
        resize_keyboard=True,
        input_field_placeholder="Telefon raqamingizni ulashing...",
    )


def otp_inline_keyboard(code: str) -> InlineKeyboardMarkup:
    """OTP xabari ostidagi inline tugmalar."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"✅  {code}  —  Nusxalash",
                callback_data=f"copy_otp:{code}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔄  Yangi Kod",
                callback_data="new_otp",
            ),
        ],
    ])


async def send_otp_message(target_message: Message, code: str, full_name: str):
    """
    OTP kodni modern dizaynda inline tugmalar bilan yuborish.
    target_message — javob yuboriladigan xabar (message yoki callback.message).
    """
    c = code
    text = (
        f"🔐  <b>Kirish kodi</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤  {full_name}\n\n"
        f"<code>  {c[0]}  {c[1]}  {c[2]}    {c[3]}  {c[4]}  {c[5]}  </code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳  <b>10 daqiqa</b> ichida amal qiladi\n"
        f"🔒  Hech kim bilan ulashmang\n\n"
        f"🌐  <a href='http://127.0.0.1:8000/login/'>shadowme.uz/login</a>"
    )
    await target_message.answer(
        text,
        reply_markup=otp_inline_keyboard(code),
        disable_web_page_preview=True,
    )


async def check_and_send_otp(
    user: TelegramUser,
    target_message: Message,
    bot: Bot,
    callback_query: CallbackQuery | None = None,
) -> bool:
    """
    Faol OTP va rate limit tekshirib OTP yuboradi.

    Tekshirish tartibi:
        1. Faol OTP bor?      → show_alert=True  (callback) | xabar (message)
        2. 1 daqiqa limit?    → show_alert=True  (callback) | xabar (message)
        3. Hammasi OK          → ack + OTP yuboradi
    """
    is_callback = callback_query is not None

    # 1️⃣ Faol OTP bormi tekshirish
    active_otp = await db_get_active_otp(user)
    if active_otp:
        remaining = await db_get_active_remaining_seconds(user)
        mins = remaining // 60
        secs = remaining % 60
        time_str = f"{mins} daqiqa {secs} soniya" if mins > 0 else f"{secs} soniya"

        if is_callback:
            await callback_query.answer(
                f"⚠️ OTP hali amal qilmoqda!\n{time_str} dan keyin eskiradi.",
                show_alert=True,
            )
        else:
            await target_message.answer(
                f"⚠️ <b>OTP kod hali amal qilmoqda!</b>\n\n"
                f"Sizga yuborilgan kod <b>{time_str}</b> dan keyin eskiradi.\n\n"
                f"Yangi kod so'rashdan oldin:\n"
                f"• Mavjud kodni ishlating, yoki\n"
                f"• Kod eskirishini kuting\n\n"
                f"🌐 <a href='http://127.0.0.1:8000/login/'>shadowme.uz/login</a>",
                disable_web_page_preview=True,
            )
        return False

    # 2️⃣ 1 daqiqa rate limit tekshirish
    if not await db_can_request_otp(user):
        wait = await db_get_wait_seconds(user)
        if is_callback:
            await callback_query.answer(
                f"⏳ {wait} soniya kuting.\n1 daqiqada 1 ta OTP beriladi.",
                show_alert=True,
            )
        else:
            await target_message.answer(
                f"⏳ <b>{wait} soniya</b> kuting.\n\n1 daqiqada faqat 1 ta OTP so'rash mumkin."
            )
        return False

    # 3️⃣ Hammasi yaxshi → callback ni ack qilib OTP yuboramiz
    if is_callback:
        await callback_query.answer("✨ Kod yaratilmoqda...", show_alert=False)

    otp = await db_create_otp(user)
    await send_otp_message(target_message, otp.code, user.full_name)
    return True


# ── /start (main_router) ─────────────────────────────────────────────────────

@main_router.message(CommandStart())
async def start_command(message: Message):
    tg_user = message.from_user

    text = (
        f"👋 Assalomu alaykum, <b>{tg_user.full_name}</b>!\n\n"
        f"🌟 <b>ShadowMe</b> ga xush kelibsiz!\n\n"
        f"Shadow method yordamida <b>Koreys</b> va <b>Ingliz</b> tillarini o'rganish platformasi.\n\n"
        f"<b>Kirish uchun:</b>\n"
        f"1️⃣ Quyidagi tugmani bosing\n"
        f"2️⃣ Telefon raqamingizni ulashing\n"
        f"3️⃣ 6 xonali OTP kodni oling\n"
        f"4️⃣ <a href='http://127.0.0.1:8000/login/'>shadowme.uz/login</a> da kodni kiriting"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 OTP Olish", callback_data="trigger_login")]
    ])
    await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)


# ── /help (main_router) ──────────────────────────────────────────────────────

@main_router.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "📖 <b>Yordam</b>\n\n"
        "Buyruqlar:\n"
        "• /start — Botni qayta ishga tushirish\n"
        "• /login — OTP kodi olish\n"
        "• /help — Ushbu yordam\n\n"
        "⚠️ <b>Muhim:</b>\n"
        "• OTP kodi 10 daqiqa amal qiladi\n"
        "• 1 daqiqada faqat 1 marta OTP so'rash mumkin\n"
        "• Har bir OTP faqat 1 marta ishlatiladi"
    )


# ── /login va trigger_login (login_router) ───────────────────────────────────

@login_router.message(Command("login"))
async def login_command(message: Message, state: FSMContext, bot: Bot):
    """/login buyrug'i — mavjud foydalanuvchi bo'lsa OTP, yangi bo'lsa kontakt so'raydi."""
    tg_user = message.from_user
    user = await db_get_user(tg_user.id)

    if user is None:
        await message.answer(
            "📱 <b>Telefon raqamingizni ulashing</b>\n\n"
            "Pastdagi tugmani bosib Telegram raqamingizni ulashing.\n"
            "Bu ma'lumotlar xavfsiz saqlanadi va faqat kirish uchun ishlatiladi.",
            reply_markup=contact_keyboard(),
        )
        await state.set_state(LoginStates.waiting_for_contact)
        return

    # Profil rasmini yangilash
    photo_url = await get_user_photo_url(bot, tg_user.id, tg_user.full_name)
    await db_update_photo(user, photo_url)

    await check_and_send_otp(user, message, bot)
    await state.clear()


@login_router.callback_query(F.data == "trigger_login")
async def trigger_login_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Inline 'OTP Olish' tugmasi bosilganda."""
    tg_user = callback.from_user
    user = await db_get_user(tg_user.id)

    if user is None:
        await callback.answer()
        await callback.message.answer(
            "📱 <b>Telefon raqamingizni ulashing</b>\n\n"
            "Pastdagi tugmani bosib Telegram raqamingizni ulashing.\n"
            "Bu ma'lumotlar xavfsiz saqlanadi va faqat kirish uchun ishlatiladi.",
            reply_markup=contact_keyboard(),
        )
        await state.set_state(LoginStates.waiting_for_contact)
        return

    # Profil rasmini yangilash
    photo_url = await get_user_photo_url(bot, tg_user.id, tg_user.full_name)
    await db_update_photo(user, photo_url)

    await check_and_send_otp(user, callback.message, bot, callback_query=callback)
    await state.clear()


@login_router.message(LoginStates.waiting_for_contact, F.contact)
async def contact_received(message: Message, state: FSMContext, bot: Bot):
    """Telefon raqami olinganda — ro'yxatdan o'tkazish va OTP yuborish."""
    tg_user = message.from_user
    contact = message.contact

    # Boshqa birovning kontaktini tekshirish
    if contact.user_id and contact.user_id != tg_user.id:
        await message.answer(
            "❌ Iltimos, <b>o'zingizning</b> telefon raqamingizni ulashing.",
            reply_markup=contact_keyboard(),
        )
        return  # LoginStates.waiting_for_contact da qoladi

    phone_number = contact.phone_number
    if not phone_number.startswith("+"):
        phone_number = "+" + phone_number

    full_name = tg_user.full_name or tg_user.first_name or "Foydalanuvchi"
    photo_url = await get_user_photo_url(bot, tg_user.id, full_name)

    user, created = await db_get_or_create_user(
        telegram_id=tg_user.id,
        full_name=tg_user.full_name or tg_user.first_name or "Foydalanuvchi",
        username=tg_user.username,
        phone_number=phone_number,
        photo_url=photo_url,
    )

    if created:
        logger.info(f"Yangi foydalanuvchi: {user.full_name} ({user.telegram_id})")

    # Keyboard ni olib tashlash
    await message.answer(
        "✅ Telefon raqami qabul qilindi!",
        reply_markup=ReplyKeyboardRemove(),
    )

    # OTP yuborish
    await check_and_send_otp(user, message, bot)
    await state.clear()


@login_router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    await message.answer(
        "❌ Jarayon bekor qilindi.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.clear()


# ── Inline tugma callbacklari (callback_router) ──────────────────────────────

@callback_router.callback_query(F.data.startswith("copy_otp:"))
async def copy_otp_callback(callback: CallbackQuery):
    """'Nusxalash' tugmasi — kodni alohida xabar sifatida yuboradi."""
    await callback.answer("✅ Kod nusxalash uchun tayyor!", show_alert=False)

    code = callback.data.split(":", 1)[1]  # "copy_otp:123456" → "123456"
    c = code
    await callback.message.answer(
        f"📋  Kodni bosib nusxalang:\n\n"
        f"<code>{c[0]} {c[1]} {c[2]}  {c[3]} {c[4]} {c[5]}</code>\n\n"
        f"<i>Yuqoridagi kodni bosing — u avtomatik nusxalanadi.</i>"
    )


@callback_router.callback_query(F.data == "new_otp")
async def new_otp_callback(callback: CallbackQuery, bot: Bot):
    """'Yangi Kod' tugmasi — faol OTP va rate limit tekshirib yangi OTP beradi."""
    tg_user = callback.from_user

    user = await db_get_user(tg_user.id)
    if user is None:
        await callback.answer("Avval /login buyrug'ini yuboring!", show_alert=True)
        return

    # check_and_send_otp ichida barcha tekshiruvlar va alert lar amalga oshadi
    await check_and_send_otp(user, callback.message, bot, callback_query=callback)


# ── Dispatcher va Bot yaratish ────────────────────────────────────────────────

def create_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    """Bot va Dispatcher yaratib qaytaradi."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        raise ValueError(
            "TELEGRAM_BOT_TOKEN sozlanmagan!\n"
            ".env fayliga: TELEGRAM_BOT_TOKEN=your_actual_token"
        )

    bot = Bot(
        token=token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )

    dp = Dispatcher()

    # Routerlarni ulash
    dp.include_routers(main_router, login_router, callback_router)

    return bot, dp


async def start_polling():
    """Botni polling rejimida ishga tushirish."""
    bot, dp = create_bot_and_dispatcher()

    logger.info("🤖 ShadowMe bot (aiogram 3) ishga tushmoqda...")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query"],
        )
    finally:
        await bot.session.close()
