# -*- coding: utf-8 -*-
"""
TEST MA'LUMOTLARI
==================
Bu yerda maktabning sinflar jadvali yoziladi. Hozircha bu TEST (namunaviy)
ma'lumot - botning ishlashini sinash uchun avtomatik generatsiya qilingan.

Haqiqiy jadvalingiz tayyor bo'lganda, shu faylni real ma'lumotlar bilan
almashtiring. Struktura juda oddiy - har bir sinf uchun, har bir kun uchun,
darslar ro'yxati:

SCHEDULE = {
    "5-A": {
        "Dushanba": [
            {"time": "08:30-09:15", "subject": "Matematika", "teacher": "Aliyev Vali", "room": "12"},
            ...
        ],
        ...
    },
    ...
}
"""

# 5 kunlik o'quv haftasi (Dushanba-Juma). Tartib MUHIM: bot sanalarni shu
# tartib bo'yicha hisoblaydi (1-element = Dushanba, ... 5-element = Juma).
# Shanba va Yakshanba - dam olish kuni.
DAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma"]

CLASSES = ["5-A", "6-B", "7-A"]

TIME_SLOTS = [
    "08:30-09:15",
    "09:25-10:10",
    "10:20-11:05",
    "11:15-12:00",
    "12:30-13:15",
]

# (o'qituvchi, fan) juftliklari - test uchun
TEACHER_POOL = [
    ("Aliyev Vali", "Matematika"),
    ("Yusupova Nilufar", "Ona tili"),
    ("Karimov Bekzod", "Tarix"),
    ("Rustamov Sardor", "Fizika"),
    ("Ergasheva Malika", "Ingliz tili"),
    ("Tosheva Dilnoza", "Biologiya"),
    ("Nazarov Jasur", "Jismoniy tarbiya"),
]


def _build_schedule():
    """Har bir sinf va kun uchun avtomatik test jadvalini yasaydi."""
    schedule = {}
    for c_idx, class_name in enumerate(CLASSES):
        schedule[class_name] = {}
        for d_idx, day in enumerate(DAYS):
            lessons = []
            # Har bir sinf/kun uchun 4 ta dars, pool bo'ylab siljitib tanlanadi
            for slot_idx, time_slot in enumerate(TIME_SLOTS[:4]):
                pool_index = (c_idx * 2 + d_idx + slot_idx) % len(TEACHER_POOL)
                teacher, subject = TEACHER_POOL[pool_index]
                room = str(10 + pool_index)
                lessons.append(
                    {
                        "time": time_slot,
                        "subject": subject,
                        "teacher": teacher,
                        "room": room,
                    }
                )
            schedule[class_name][day] = lessons
    return schedule


SCHEDULE = _build_schedule()
