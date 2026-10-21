# Maktab dars jadvali boti

Telegram bot: o'quvchi va o'qituvchilar uchun dars jadvali, o'qituvchi/sinf
qidirish (hozir qayerda ekani real vaqtda), admin panel.

> ⚠️ `data.py` da hozircha **test (namunaviy) ma'lumotlar** bor: 3 ta sinf
> (5-A, 6-B, 7-A) va 7 ta o'qituvchi. Haqiqiy jadval bilan almashtiring.

## Imkoniyatlar

**🗓 5 kunlik o'quv haftasi (Dushanba–Juma).** Jadval har hafta bir xil. Kun
tugmalari sanasi bilan ko'rinadi (masalan "Dushanba 26.10") va
**Bu hafta / Keyingi hafta** tugmalari bor. Shanba va Yakshanba — dam olish
kuni: bot shuni aytadi va keyingi haftaning Dushanba jadvalini ko'rsatadi.

**👨‍🎓 O'quvchi** — sinfini tanlaydi; bugungi jadval avtomatik chiqadi, istalgan
kunni va haftani tugma bilan ochadi; o'qituvchini qidiradi (hozir qaysi
sinfda/xonada ekanini + haftalik jadvalini ko'radi); sinfni qidiradi (hozir
qaysi darsda).

**👨‍🏫 O'qituvchi** — ismini tanlaydi; o'z jadvalini (bugun + istalgan kun),
qaysi sinflarda dars berishini ko'radi; boshqa o'qituvchi/sinfni qidiradi.

**🔧 Admin** (`/admin`) — hammaga xabar yuborish (bekor qilish tugmasi bilan),
texnik ishlar rejimini yoqish/o'chirish, statistika.

**Buyruqlar:** `/start`, `/help`, `/id`, `/admin`.

## 1. Bot yaratish
[@BotFather](https://t.me/BotFather) → `/newbot` → tokenni oling.
Token **sir** — uni hech qachon GitHub'ga yuklamang. Oshkor bo'lsa, BotFather'da
`/revoke` qiling.

## 2. Lokal ishga tushirish
Python 3.12 tavsiya etiladi.

```bash
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
# .env ni oching va BOT_TOKEN, ADMIN_IDS ni to'ldiring
python bot.py
```

Telegram ID'ingizni bilmasangiz — botga `/id` yuboring. Bir nechta admin:
`ADMIN_IDS=111111,222222`.

## 3. Render'ga joylashtirish
1. Kodni GitHub'ga yuklang (`.env` yuklanmaydi — `.gitignore` himoya qiladi).
2. Render'da yangi **Background Worker** yarating (pullik reja kerak bo'lishi mumkin) va repo'ni bog'lang.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python bot.py`
5. Environment: `BOT_TOKEN`, `ADMIN_IDS`, `PYTHON_VERSION=3.12.7`
6. Deploy.

(`Procfile` Render'da ishlatilmaydi — u Heroku uchun. Python versiyasi
`.python-version` yoki `PYTHON_VERSION` orqali beriladi.)

## 4. Jadvalni yangilash
`data.py` dagi `SCHEDULE` ni haqiqiy ma'lumot bilan almashtiring (struktura fayl
boshidagi izohda). Jadval o'zgarsa, shu faylni tahrirlab GitHub'ga yuklaysiz —
hamma haftalar uchun yangilanadi. `DAYS` (Dushanba–Juma, shu tartibda) ichidagi
kun nomlari bilan bir xil yozing.
Tugmalar ro'yxat indeksiga asoslangan — uzun/kirill ismlar ham ishlaydi.

## 5. Ma'lumot saqlash
Foydalanuvchilar ro'yxati, texnik rejim va statistika `state.json` da saqlanadi.
Render'da qayta deploy qilinganda bu fayl yo'qolishi mumkin (jadval esa
`data.py` da xavfsiz). Doimiy saqlash kerak bo'lsa, `STATE_FILE` ni doimiy
diskka yo'naltiring.

## Fayllar
```
bot.py            # handler'lar, tugmalar, admin panel
data.py           # jadval ma'lumotlari (shu yerni o'zgartirasiz)
logic.py          # jadval qidirish, Toshkent vaqti bo'yicha "hozir" hisobi
storage.py        # foydalanuvchilar, texnik rejim, statistika (JSON)
requirements.txt  # python-telegram-bot, tzdata, python-dotenv
.env.example      # sozlamalar namunasi
.gitignore        # .env, state.json, *.pyc ni himoya qiladi
```
