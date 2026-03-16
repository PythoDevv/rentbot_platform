# Server Deployment

Bu loyiha hozirgi holatda legacy `kbot` repo bilan birga ishlaydi. Eng xavfsiz deploy sxemasi:

```text
/opt/kbot/
|-- app.py
|-- requirements.txt
|-- ...
`-- rentbot_platform/
    |-- Dockerfile
    |-- docker-compose.yml
    `-- .env
```

`rentbot_platform` papkasi legacy repo ichida bo'lishi kerak. Hozirgi `docker-compose.yml` build konteksti yuqoridagi `kbot` ildiziga qaraydi.

Agar bu repo legacy `kbot` ga sibling bo'lib tursa, `.env` ichida `LEGACY_REPO_ROOT=../kbot` deb ko'rsating.

## 1. Serverga fayllarni joylash

```bash
sudo mkdir -p /opt/kbot
sudo chown -R $USER:$USER /opt/kbot
cd /opt/kbot
git clone <legacy-kbot-repo> .
git clone <this-repo> rentbot_platform
cd rentbot_platform
cp .env.example .env
```

## 2. `.env` ni to'ldirish

Kamida quyidagilarni o'zgartiring:

- `SECRET_KEY`
- `SUPERADMIN_PASSWORD`
- `DATABASE_ADMIN_URL`
- `PUBLIC_BASE_URL`
- `ADMINS`
- `DB_USER`
- `DB_PASS`
- `DB_NAME`
- `DB_HOST`
- `DB_PORT`
- `ip`

Compose uchun qo'shimcha yo'l sozlamalari:

- `LEGACY_REPO_ROOT=..`
- `PLATFORM_DIR=rentbot_platform`
- `PLATFORM_DOCKERFILE=Dockerfile`

Agar papka nomini o'zgartirsangiz, ikkala qiymatni ham mos ravishda yangilang.

`DATABASE_ADMIN_URL` tavsiya etiladi. Platform har yangi bot uchun alohida Postgres database yaratadi. Misol:

```env
DATABASE_ADMIN_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/postgres
```

## 3. Deploydan oldin tekshirish

```bash
./scripts/check_deploy_ready.sh
```

Skript `.env`, legacy fayllar va Docker Compose kerakli yo'llarini tekshiradi.

## 4. Konteynerlarni ishga tushirish

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f app
```

Panel default ravishda `8000` portda ko'tariladi.

## 5. Nginx reverse proxy

Namuna konfiguratsiya: [deploy/nginx.rentbot.conf.example](/home/ilyos/bots/rentbot_platform/deploy/nginx.rentbot.conf.example)

Minimal oqim:

```bash
sudo cp deploy/nginx.rentbot.conf.example /etc/nginx/sites-available/rentbot
sudo ln -s /etc/nginx/sites-available/rentbot /etc/nginx/sites-enabled/rentbot
sudo nginx -t
sudo systemctl reload nginx
```

Keyin `certbot` yoki siz ishlatayotgan TLS usuli bilan HTTPS ulang.

## 6. Tekshirish

```bash
curl http://127.0.0.1:8000/healthz
```

Kutilgan javob:

```json
{"status":"ok"}
```

## Muammolar

- `Legacy bot entrypoint topilmadi`: `app.py` legacy repo ildizida yo'q yoki loyiha noto'g'ri joyga ko'chirilgan.
- `requirements.txt` topilmadi: image legacy repo dependency faylini ko'ra olmayapti.
- `PUBLIC_BASE_URL` noto'g'ri: panel ichidagi linklar va legacy bot callback URL'lari buziladi.
