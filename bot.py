# -*- coding: utf-8 -*-
"""
Maktab dars jadvali va o'qituvchi/sinf qidirish boti.

Ishga tushirish:
    BOT_TOKEN=xxxx ADMIN_IDS=123456789 python bot.py
yoki .env faylga BOT_TOKEN va ADMIN_IDS yozib, shunchaki:  python bot.py
"""

import asyncio
import html
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

try:  # lokal ishga tushirishda .env faylni avtomatik o'qiydi
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv o'rnatilmagan bo'lsa ham bot ishlayveradi
    pass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import storage
from data import DAYS
from logic import (
    current_lesson_for_class,
    current_status_for_teacher,
    date_for_day,
    default_week_offset,
    format_date,
    get_all_classes,
    get_all_teachers,
    get_class_schedule,
    get_teacher_classes,
    get_teacher_schedule,
    get_teacher_subject,
    now_tashkent,
    today_day_name,
    today_off_name,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # tokenni logga chiqarmaslik uchun
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()


def _parse_admin_ids(raw: str):
    ids = set()
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        if part.lstrip("-").isdigit():
            ids.add(int(part))
        else:
            logger.warning("ADMIN_IDS ichida noto'g'ri qiymat tashlab ketildi: %r", part)
    return ids


ADMIN_IDS = _parse_admin_ids(os.environ.get("ADMIN_IDS", ""))

MAX_TEXT = 4000  # Telegram xabar chegarasi 4096

MAINTENANCE_TEXT = (
    "🔧 Bot hozir texnik ishlar tufayli vaqtincha ishlamayapti. "
    "Iltimos, keyinroq urinib ko'ring."
)
SESSION_LOST_TEXT = (
    "⚠️ Sessiya tugagan (bot yangilangan bo'lishi mumkin).\n"
    "Iltimos, qaytadan boshlang — kim sifatida kirmoqchisiz?"
)

# Bu prefikslarda callback_data ichida ro'yxat INDEKSI turadi (nomi emas) —
# Telegram callback_data 64 baytdan oshmasligi uchun.
INDEXED_PREFIXES = {"class", "teacher_login", "search_teacher", "search_class", "day"}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def pick(items, idx_str):
    """Indeks (matn) bo'yicha ro'yxatdan elementni xavfsiz oladi, topilmasa None."""
    try:
        idx = int(idx_str)
    except (TypeError, ValueError):
        return None
    if 0 <= idx < len(items):
        return items[idx]
    return None


# ---------------------------------------------------------------------------
# Klaviaturalar
# ---------------------------------------------------------------------------

def role_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👨‍🎓 O'quvchiman", callback_data="role:student")],
            [InlineKeyboardButton("👨‍🏫 O'qituvchiman", callback_data="role:teacher")],
        ]
    )


def classes_keyboard(prefix: str, back_callback: str = "back:role"):
    buttons = [
        [InlineKeyboardButton(c, callback_data=f"{prefix}:{i}")]
        for i, c in enumerate(get_all_classes())
    ]
    buttons.append([InlineKeyboardButton("⬅️ Orqaga", callback_data=back_callback)])
    return InlineKeyboardMarkup(buttons)


def teachers_keyboard(prefix: str, back_callback: str = "back:role"):
    buttons = [
        [InlineKeyboardButton(t, callback_data=f"{prefix}:{i}")]
        for i, t in enumerate(get_all_teachers())
    ]
    buttons.append([InlineKeyboardButton("⬅️ Orqaga", callback_data=back_callback)])
    return InlineKeyboardMarkup(buttons)


def student_menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📅 Jadvalim", callback_data="stu:schedule")],
            [InlineKeyboardButton("🔍 O'qituvchini qidirish", callback_data="stu:search_teacher")],
            [InlineKeyboardButton("🔍 Sinfni qidirish", callback_data="stu:search_class")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="back:role")],
        ]
    )


def teacher_menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📅 Jadvalim", callback_data="tea:schedule")],
            [InlineKeyboardButton("🏫 Qaysi sinflarda dars beraman", callback_data="tea:my_classes")],
            [InlineKeyboardButton("🔍 Boshqa o'qituvchini qidirish", callback_data="tea:search_teacher")],
            [InlineKeyboardButton("🔍 Sinfni qidirish", callback_data="tea:search_class")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="back:role")],
        ]
    )


def menu_back_callback(role: str) -> str:
    return "back:student_menu" if role == "student" else "back:teacher_menu"


def back_to_menu_keyboard(role: str):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Orqaga", callback_data=menu_back_callback(role))]]
    )


def day_keyboard(role: str, week: int = 0):
    """Kun tugmalari (sanasi bilan) + 'Bu hafta / Keyingi hafta' almashtirgich."""
    buttons, row = [], []
    for i, day in enumerate(DAYS):
        label = f"{day} {format_date(date_for_day(i, week))}"
        row.append(InlineKeyboardButton(label, callback_data=f"day:{i}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(
        [
            InlineKeyboardButton(
                ("✅ " if week == 0 else "") + "Bu hafta", callback_data="week:0"
            ),
            InlineKeyboardButton(
                ("✅ " if week == 1 else "") + "Keyingi hafta", callback_data="week:1"
            ),
        ]
    )
    buttons.append(
        [InlineKeyboardButton("⬅️ Menyuga qaytish", callback_data=menu_back_callback(role))]
    )
    return InlineKeyboardMarkup(buttons)


def admin_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📢 Xabar yuborish", callback_data="admin:broadcast")],
            [InlineKeyboardButton("⏸ Texnik ishlar rejimi", callback_data="admin:maintenance")],
            [InlineKeyboardButton("📊 Statistika", callback_data="admin:stats")],
        ]
    )


def cancel_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin:cancel")]]
    )


# ---------------------------------------------------------------------------
# Matn shakllantirish
# ---------------------------------------------------------------------------

def _day_title(day: str, date_str: str = ""):
    return f"{day}, {date_str}" if date_str else day


def format_class_day(class_name: str, day: str, lessons, date_str: str = ""):
    title = _day_title(day, date_str)
    if not lessons:
        return f"📅 {class_name} sinf — {title}\n\nBu kuni dars yo'q."
    lines = [f"📅 {class_name} sinf — {title}\n"]
    for lesson in lessons:
        lines.append(
            f"⏰ {lesson['time']} | 📚 {lesson['subject']} | "
            f"👨‍🏫 {lesson['teacher']} | 🚪 {lesson['room']}-xona"
        )
    return "\n".join(lines)


def format_teacher_day(teacher_name: str, subject: str, day: str, lessons, date_str: str = ""):
    title = _day_title(day, date_str)
    if not lessons:
        return f"📅 {teacher_name} ({subject}) — {title}\n\nBu kuni dars yo'q."
    lines = [f"📅 {teacher_name} ({subject}) — {title}\n"]
    for lesson in lessons:
        lines.append(
            f"⏰ {lesson['time']} | 🏫 {lesson['class']} sinf | "
            f"📚 {lesson['subject']} | 🚪 {lesson['room']}-xona"
        )
    return "\n".join(lines)


def format_teacher_card(teacher_name: str):
    subject = get_teacher_subject(teacher_name)
    lesson, msg = current_status_for_teacher(teacher_name)
    now_str = now_tashkent().strftime("%H:%M")
    header = f"👨‍🏫 {teacher_name} — {subject} fani o'qituvchisi\n\n"
    if lesson:
        status = (
            f"🟢 Hozir ({now_str}): {lesson['class']} sinfda, "
            f"{lesson['subject']} darsida, {lesson['room']}-xonada\n\n"
        )
    else:
        status = f"🔴 Hozir ({now_str}): {msg}\n\n"

    schedule = get_teacher_schedule(teacher_name)
    lines = ["📋 Haftalik jadvali:"]
    for day in DAYS:
        day_lessons = schedule.get(day, [])
        if day_lessons:
            lines.append(f"\n{day}:")
            for lesson_item in day_lessons:
                lines.append(
                    f"  ⏰ {lesson_item['time']} | 🏫 {lesson_item['class']} | "
                    f"🚪 {lesson_item['room']}-xona"
                )
    return header + status + "\n".join(lines)


def format_class_card(class_name: str):
    lesson, msg = current_lesson_for_class(class_name)
    now_str = now_tashkent().strftime("%H:%M")
    header = f"🏫 {class_name} sinf\n\n"
    if lesson:
        status = (
            f"🟢 Hozir ({now_str}): {lesson['subject']} darsida, "
            f"{lesson['teacher']} o'qituvchi, {lesson['room']}-xonada"
        )
    else:
        status = f"🔴 Hozir ({now_str}): {msg}"
    return header + status


def week_line(week: int) -> str:
    start = format_date(date_for_day(0, week))
    end = format_date(date_for_day(len(DAYS) - 1, week))
    name = "Bu hafta" if week == 0 else "Keyingi hafta"
    return f"📆 {name}: {start} – {end}"


def render_schedule_text(ud):
    """Hozir ko'rilayotgan (sinf/o'qituvchi) uchun tanlangan hafta va kun jadvali matni.

    ud["viewing"], ud["week"] (0/1) va ud["day"] (DAYS indeksi) ishlatiladi.
    Ma'lumot yetarli bo'lmasa None qaytaradi.
    """
    viewing = ud.get("viewing") or {}
    week = ud.get("week", 0)
    day_idx = ud.get("day", 0)
    if viewing.get("type") not in ("class", "teacher") or not (0 <= day_idx < len(DAYS)):
        return None
    day = DAYS[day_idx]
    date_str = format_date(date_for_day(day_idx, week))
    if week == 0 and today_day_name() == day:
        date_str += " (bugun)"
    if viewing["type"] == "class":
        lessons = get_class_schedule(viewing["id"], day)
        text = format_class_day(viewing["id"], day, lessons, date_str)
    else:
        schedule = get_teacher_schedule(viewing["id"])
        subject = get_teacher_subject(viewing["id"])
        text = format_teacher_day(viewing["id"], subject, day, schedule.get(day, []), date_str)
    return text + "\n\n" + week_line(week)


def start_schedule_view(ud, view_type: str, ident: str):
    """Jadval ko'rinishini boshlaydi: bugun (yoki dam olish kunida - keyingi haftaning Dushanbasi).

    Qaytaradi: (matn, hafta). Dam olish kunida matn boshiga izoh qo'shiladi.
    """
    ud["viewing"] = {"type": view_type, "id": ident}
    ud["week"] = default_week_offset()
    today = today_day_name()
    if today is None:
        ud["day"] = 0
        prefix = f"🌿 Bugun {today_off_name()} — dam olish kuni.\nKeyingi hafta jadvali:\n\n"
        suffix = ""
    else:
        ud["day"] = DAYS.index(today) if today in DAYS else 0
        prefix = ""
        suffix = "\n\n(Bugungi kun avtomatik ko'rsatildi)"
    return prefix + (render_schedule_text(ud) or "") + suffix


# ---------------------------------------------------------------------------
# Yordamchilar
# ---------------------------------------------------------------------------

async def safe_edit(query, text: str, reply_markup=None):
    """Xabarni tahrirlaydi. 'Message is not modified' xatosini jim o'tkazadi."""
    try:
        await query.edit_message_text(text[:MAX_TEXT], reply_markup=reply_markup)
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            return
        raise


async def ask_role_again(query):
    """Foydalanuvchi sessiyasi yo'qolgan bo'lsa (masalan, bot qayta ishga tushgan)."""
    await safe_edit(query, SESSION_LOST_TEXT, reply_markup=role_keyboard())


def track(update: Update):
    """Foydalanuvchini broadcast ro'yxatida saqlab qo'yadi."""
    chat = update.effective_chat
    if chat is not None:
        storage.register_user(chat.id)


# ---------------------------------------------------------------------------
# Umumiy komandalar
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(update)
    message = update.effective_message

    if storage.is_maintenance() and not is_admin(update.effective_user.id):
        await message.reply_text(MAINTENANCE_TEXT)
        return

    context.user_data.clear()
    await message.reply_text(
        "Assalomu alaykum! 👋\nKim sifatida kirmoqchisiz?",
        reply_markup=role_keyboard(),
    )


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        f"Sizning Telegram ID'ingiz: <code>{update.effective_user.id}</code>",
        parse_mode=ParseMode.HTML,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "📌 Buyruqlar:\n"
        "/start — botni boshlash\n"
        "/id — Telegram ID'ingizni ko'rish\n"
        "/help — yordam\n"
        "/admin — admin panel (faqat adminlar uchun)"
    )


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not is_admin(update.effective_user.id):
        await message.reply_text("⛔️ Bu buyruq faqat adminlar uchun.")
        return
    await message.reply_text("🔧 Admin panel:", reply_markup=admin_keyboard())


async def handle_admin_callback(query, context: ContextTypes.DEFAULT_TYPE, data: str):
    if data == "admin:broadcast":
        context.user_data["awaiting_broadcast"] = True
        await safe_edit(
            query,
            "✍️ Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing:",
            reply_markup=cancel_keyboard(),
        )
    elif data == "admin:cancel":
        context.user_data["awaiting_broadcast"] = False
        await safe_edit(query, "🔧 Admin panel:", reply_markup=admin_keyboard())
    elif data == "admin:maintenance":
        new_state = storage.toggle_maintenance()
        status_text = (
            "🔴 YOQILDI (bot vaqtincha o'chirilgan)"
            if new_state
            else "🟢 O'CHIRILDI (bot ishlamoqda)"
        )
        await safe_edit(
            query, f"Texnik ishlar rejimi: {status_text}", reply_markup=admin_keyboard()
        )
    elif data == "admin:stats":
        stats = storage.get_stats()
        lines = [f"📊 Statistika\n\n👥 Foydalanuvchilar soni: {stats['user_count']}\n"]
        if stats["action_counts"]:
            lines.append("📈 Funksiyalardan foydalanish:")
            for action, count in sorted(stats["action_counts"].items(), key=lambda x: -x[1]):
                lines.append(f"  • {action}: {count}")
        else:
            lines.append("Hali statistika yo'q.")
        await safe_edit(query, "\n".join(lines), reply_markup=admin_keyboard())


async def run_broadcast(bot, admin_chat_id: int, text: str):
    """Xabarni hammaga yuboradi (alohida vazifa sifatida - boshqa foydalanuvchilarni to'sib qo'ymaydi)."""
    sent = failed = blocked = 0
    for chat_id in storage.get_all_users():
        for attempt in range(2):
            try:
                await bot.send_message(chat_id=chat_id, text=f"📢 E'lon:\n\n{text}")
                sent += 1
                break
            except RetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 1)
                if attempt == 1:
                    failed += 1
            except Forbidden:
                storage.remove_user(chat_id)  # bot bloklangan - ro'yxatdan chiqaramiz
                blocked += 1
                break
            except TelegramError:
                failed += 1
                break
        await asyncio.sleep(0.05)  # Telegram tezlik chegarasidan oshmaslik uchun

    try:
        await bot.send_message(
            chat_id=admin_chat_id,
            text=(
                "✅ Xabar yuborish yakunlandi.\n"
                f"Muvaffaqiyatli: {sent}\n"
                f"Botni bloklaganlar (ro'yxatdan o'chirildi): {blocked}\n"
                f"Boshqa xatolar: {failed}"
            ),
        )
    except TelegramError:
        logger.exception("Admin'ga broadcast hisobotini yuborib bo'lmadi")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oddiy matn: admin xabar yozayotgan bo'lsa - broadcast, aks holda yo'naltirish."""
    message = update.effective_message
    user = update.effective_user

    if is_admin(user.id) and context.user_data.get("awaiting_broadcast"):
        text = (message.text or "").strip()
        if not text:
            return
        if len(text) > MAX_TEXT - 50:
            await message.reply_text(
                f"❗️ Xabar juda uzun ({len(text)} belgi). {MAX_TEXT - 50} belgidan qisqaroq yozing."
            )
            return
        context.user_data["awaiting_broadcast"] = False
        users_count = len(storage.get_all_users())
        await message.reply_text(
            f"📤 Yuborish boshlandi ({users_count} ta foydalanuvchi). Tugagach hisobot beraman."
        )
        context.application.create_task(
            run_broadcast(context.bot, update.effective_chat.id, text), update=update
        )
        return

    if storage.is_maintenance() and not is_admin(user.id):
        await message.reply_text(MAINTENANCE_TEXT)
        return

    await message.reply_text(
        "Botdan foydalanish uchun /start ni bosing yoki /help ni ko'ring."
    )


# ---------------------------------------------------------------------------
# Callback dispatcher
# ---------------------------------------------------------------------------

def stat_key(data: str) -> str:
    """Statistika uchun kalit: indeksli tugmalarda faqat prefiks (raqamsiz)."""
    prefix = data.split(":", 1)[0]
    if prefix in INDEXED_PREFIXES or ":" not in data:
        return prefix
    return data


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    user_id = update.effective_user.id
    track(update)

    if storage.is_maintenance() and not is_admin(user_id):
        await safe_edit(query, "🔧 Bot hozir texnik ishlar tufayli vaqtincha ishlamayapti.")
        return

    if data.startswith("admin:"):
        if not is_admin(user_id):
            await safe_edit(query, "⛔️ Ruxsat yo'q.")
            return
        await handle_admin_callback(query, context, data)
        return

    storage.log_action(stat_key(data))
    ud = context.user_data

    # --- Rol tanlash ---
    if data == "role:student":
        ud.clear()
        ud["role"] = "student"
        await safe_edit(query, "Sinfingizni tanlang:", reply_markup=classes_keyboard("class"))

    elif data == "role:teacher":
        ud.clear()
        ud["role"] = "teacher"
        await safe_edit(
            query, "Ismingizni tanlang:", reply_markup=teachers_keyboard("teacher_login")
        )

    elif data.startswith("class:"):
        class_name = pick(get_all_classes(), data.split(":", 1)[1])
        if class_name is None:
            await ask_role_again(query)
            return
        ud["class"] = class_name
        ud["role"] = "student"
        await safe_edit(
            query, f"Xush kelibsiz, {class_name} sinf! 🎓", reply_markup=student_menu_keyboard()
        )

    elif data.startswith("teacher_login:"):
        teacher_name = pick(get_all_teachers(), data.split(":", 1)[1])
        if teacher_name is None:
            await ask_role_again(query)
            return
        ud["teacher"] = teacher_name
        ud["role"] = "teacher"
        await safe_edit(
            query, f"Xush kelibsiz, {teacher_name}! 👋", reply_markup=teacher_menu_keyboard()
        )

    # --- O'quvchi menyusi ---
    elif data == "stu:schedule":
        class_name = ud.get("class")
        if not class_name:
            await ask_role_again(query)
            return
        text = start_schedule_view(ud, "class", class_name)
        await safe_edit(query, text, reply_markup=day_keyboard("student", ud["week"]))

    elif data in ("stu:search_teacher", "tea:search_teacher"):
        role = ud.get("role", "student")
        await safe_edit(
            query,
            "O'qituvchini tanlang:",
            reply_markup=teachers_keyboard("search_teacher", menu_back_callback(role)),
        )

    elif data in ("stu:search_class", "tea:search_class"):
        role = ud.get("role", "student")
        await safe_edit(
            query,
            "Sinfni tanlang:",
            reply_markup=classes_keyboard("search_class", menu_back_callback(role)),
        )

    # --- O'qituvchi menyusi ---
    elif data == "tea:schedule":
        teacher_name = ud.get("teacher")
        if not teacher_name:
            await ask_role_again(query)
            return
        text = start_schedule_view(ud, "teacher", teacher_name)
        await safe_edit(query, text, reply_markup=day_keyboard("teacher", ud["week"]))

    elif data == "tea:my_classes":
        teacher_name = ud.get("teacher")
        if not teacher_name:
            await ask_role_again(query)
            return
        classes = get_teacher_classes(teacher_name)
        if classes:
            text = "🏫 Siz dars beradigan sinflar:\n\n" + "\n".join(f"• {c}" for c in classes)
        else:
            text = "Hozircha hech qanday sinfda darsingiz topilmadi."
        await safe_edit(query, text, reply_markup=back_to_menu_keyboard("teacher"))

    # --- Qidiruv natijalari ---
    elif data.startswith("search_teacher:"):
        name = pick(get_all_teachers(), data.split(":", 1)[1])
        if name is None:
            await ask_role_again(query)
            return
        role = ud.get("role", "student")
        await safe_edit(query, format_teacher_card(name), reply_markup=back_to_menu_keyboard(role))

    elif data.startswith("search_class:"):
        name = pick(get_all_classes(), data.split(":", 1)[1])
        if name is None:
            await ask_role_again(query)
            return
        role = ud.get("role", "student")
        await safe_edit(query, format_class_card(name), reply_markup=back_to_menu_keyboard(role))

    # --- Kun tanlash (jadval ichida) ---
    elif data.startswith("day:"):
        day = pick(DAYS, data.split(":", 1)[1])
        role = ud.get("role", "student")
        if day is None or not ud.get("viewing"):
            await ask_role_again(query)
            return
        ud["day"] = DAYS.index(day)
        text = render_schedule_text(ud)
        if text is None:
            await ask_role_again(query)
            return
        await safe_edit(query, text, reply_markup=day_keyboard(role, ud.get("week", 0)))

    # --- Hafta almashtirish (Bu hafta / Keyingi hafta) ---
    elif data in ("week:0", "week:1"):
        role = ud.get("role", "student")
        if not ud.get("viewing"):
            await ask_role_again(query)
            return
        ud["week"] = int(data.split(":", 1)[1])
        text = render_schedule_text(ud)
        if text is None:
            await ask_role_again(query)
            return
        await safe_edit(query, text, reply_markup=day_keyboard(role, ud["week"]))

    # --- Orqaga qaytish ---
    elif data == "back:role":
        ud.clear()
        await safe_edit(query, "Kim sifatida kirmoqchisiz?", reply_markup=role_keyboard())

    elif data == "back:student_menu":
        if not ud.get("class"):
            await ask_role_again(query)
            return
        await safe_edit(query, "Menyu:", reply_markup=student_menu_keyboard())

    elif data == "back:teacher_menu":
        if not ud.get("teacher"):
            await ask_role_again(query)
            return
        await safe_edit(query, "Menyu:", reply_markup=teacher_menu_keyboard())

    else:
        logger.warning("Noma'lum callback: %r", data)
        await ask_role_again(query)


# ---------------------------------------------------------------------------
# Xatolarni qayta ishlash va main
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Handler ichida xatolik:", exc_info=context.error)
    # Tarmoq uzilishlari uchun foydalanuvchiga xabar yubormaymiz
    if isinstance(context.error, NetworkError):
        return
    if isinstance(update, Update) and update.effective_chat is not None:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ Kutilmagan xatolik yuz berdi. Iltimos, /start ni bosib qaytadan urinib ko'ring.",
            )
        except TelegramError:
            pass


class _HealthHandler(BaseHTTPRequestHandler):
    """Render Web Service kutadigan oddiy javob: har qanday GET/HEAD ga 200 OK."""

    def _reply(self, with_body: bool):
        payload = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if with_body:
            self.wfile.write(payload)

    def do_GET(self):
        self._reply(True)

    def do_HEAD(self):
        self._reply(False)

    def log_message(self, *args):  # logni to'ldirmaslik uchun
        pass


def start_health_server():
    """PORT o'zgaruvchisi bo'lsa (Render Web Service), kichik HTTP server ishga tushiradi.

    Render Web Service ochiq port bo'lmasa deployni muvaffaqiyatsiz deb hisoblaydi.
    Lokal ishga tushirishda va Background Worker'da PORT bo'lmasa, hech narsa qilmaydi.
    """
    raw_port = os.environ.get("PORT", "").strip()
    if not raw_port:
        return None
    try:
        port = int(raw_port)
        server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    except (ValueError, OSError) as exc:
        logger.warning("Health server ishga tushmadi (PORT=%r): %s", raw_port, exc)
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("Health server %s-portda ishga tushdi", port)
    return server


def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)
    return app


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable topilmadi. "
            "BotFather'dan olingan tokenni BOT_TOKEN sifatida bering."
        )
    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS bo'sh — admin panel hech kimga ochiq bo'lmaydi.")

    start_health_server()  # faqat PORT bo'lsa (Render Web Service)
    app = build_application()
    logger.info("Bot ishga tushdi (polling rejimida)...")
    app.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,  # bot o'chiq paytda yig'ilib qolgan eski xabarlarni o'tkazib yuboradi
    )


if __name__ == "__main__":
    main()
