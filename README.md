# RentBot Platform

`FastAPI` asosidagi multi-tenant bot platforma. Bitta admin panel orqali yangi bot qo'shish, botni yoqish/o'chirish, restart qilish va har bot uchun alohida admin loginlari yaratish mumkin. Hozirgi runtime har tenant uchun ildizdagi legacy `kbot/app.py` botini alohida process sifatida ishga tushiradi.

## Nima tayyor

- `FastAPI` asosidagi async admin panel
- Login/parol bilan sessiya auth
- Superadmin va tenant-admin rollari
- Har bot uchun alohida legacy `kbot` process runner
- Har bot uchun alohida legacy database sozlash
- Admin paneldan userlarni `CSV` va `JSON` formatda export/import qilish
- Paneldan yangi bot qo'shish
- Botni yoqish/o'chirish va restart qilish
- Docker va `docker-compose` bilan ishga tushirish

## Arxitektura

- `app/main.py`: FastAPI ilova va startup lifecycle
- `app/services/bot_runtime.py`: legacy `kbot` process registry
- `app/services/tenant_db.py`: per-bot database boshqaruvi va user import/export
- `app/web/routers`: panel route'lari
- `app/models.py`: tenant, admin va membership modellari

## Tez ishga tushirish

1. `.env.example` ni `.env` qilib ko'chiring va qiymatlarni to'ldiring.
2. `PUBLIC_BASE_URL` ga HTTPS manzilni yozing. Masalan: `https://evonne-overparticular-nasir.ngrok-free.dev`
3. Legacy bot uchun kerak bo'ladigan `ADMINS`, `DB_*` va `ip` qiymatlari to'ldirilganini tekshiring.
4. Agar repo legacy `kbot` ichida nested bo'lmasa, `.env` da `LEGACY_REPO_ROOT=../kbot` kabi yo'lni yozing.
5. Agar platform useri `CREATE DATABASE` huquqiga ega bo'lmasa, `DATABASE_ADMIN_URL` ni admin credential bilan to'ldiring.
6. `docker compose up --build -d`
7. Panel: `http://localhost:8000/login`
8. Superadmin login/parol `.env` dan olinadi.

## Serverga deploy

Server deploy uchun loyiha legacy `kbot` repo ichida `rentbot_platform/` papkasi sifatida joylashishi kerak. To'liq ko'rsatma: [DEPLOY_SERVER.md](/home/ilyos/bots/rentbot_platform/DEPLOY_SERVER.md)

## Muhim izoh

- Siz polling talab qilganingiz uchun runner har botni alohida legacy process sifatida boshqaradi.
- Bitta serverda ko'p bot ko'tarish mumkin, lekin bu holatda `1` ta web process ishlatish kerak, aks holda bot processlari dublikat bo'ladi.
- Hozirgi yondashuv `kbot` ichidagi barcha handler va state'larni qayta yozmasdan ishlatadi.

## Keyingi kuchli qadamlar

1. Bot settings uchun ko'proq CRUD qo'shish
2. Har tenant uchun audit log va billing qo'shish
3. Har import/export uchun background job va audit log qo'shish
