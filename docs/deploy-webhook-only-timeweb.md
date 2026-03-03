# Инструкция: webhook-only backend на Ubuntu (Timeweb Cloud)

Цель: поднять только backend для приема лидов по webhook и записи в PostgreSQL.

Сценарий: провайдер отправляет лиды на ваш URL:
`POST /api/provider-test/{WEBHOOK_SECRET}`

## 0) Что подготовить заранее

- Публичный IP нового сервера.
- Технический домен (или поддомен), который указывает на IP сервера.
- Доступ к репозиторию проекта.
- Сильные секреты для `.env`.

---

## 1) Timeweb Cloud: сервер и домен

1. Создайте облачный сервер с Ubuntu 22.04 или 24.04.
2. Откройте в правилах сети порты:
   - `22` (SSH)
   - `80` (HTTP)
   - `443` (HTTPS, можно включить сразу)
3. В DNS создайте A-запись:
   - Имя: `tech-leads` (пример)
   - Значение: `<SERVER_PUBLIC_IP>`
4. Подождите обновление DNS и проверьте:

```bash
nslookup tech-leads.example.ru
```

Если IP совпадает с сервером, можно продолжать.

---

## 2) Первичный вход и установка пакетов

```bash
ssh root@<SERVER_PUBLIC_IP>
apt update && apt install -y git python3 python3-venv python3-pip nginx postgresql postgresql-contrib
```

---

## 3) Клонирование проекта и Python-зависимости

```bash
cd /opt
git clone <REPO_URL> MB_LK_leads
cd /opt/MB_LK_leads

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4) PostgreSQL: создание БД и пользователя

```bash
sudo -u postgres psql
```

Внутри `psql`:

```sql
CREATE USER mb_lk_leads_app WITH PASSWORD 'CHANGE_ME_STRONG_DB_PASSWORD';
CREATE DATABASE mb_lk_leads_prod OWNER mb_lk_leads_app;
GRANT ALL PRIVILEGES ON DATABASE mb_lk_leads_prod TO mb_lk_leads_app;
\q
```

Проверка подключения:

```bash
psql -h 127.0.0.1 -p 5432 -U mb_lk_leads_app -d mb_lk_leads_prod
```

---

## 5) Готовый `.env` (шаблон под вставку)

Файл: `/opt/MB_LK_leads/.env`

```env
# Обязательный секрет для webhook URL.
WEBHOOK_SECRET=CHANGE_ME_VERY_LONG_RANDOM_SECRET

# База данных PostgreSQL (локально на этом же сервере).
DATABASE_URL=postgresql+psycopg://mb_lk_leads_app:CHANGE_ME_STRONG_DB_PASSWORD@127.0.0.1:5432/mb_lk_leads_prod

# Секрет для JWT (пусть будет длинная случайная строка).
AUTH_SECRET=CHANGE_ME_ANOTHER_LONG_RANDOM_SECRET

# Для webhook-only можно оставить ваш домен.
CORS_ORIGINS=https://tech-leads.example.ru

# Необязательные, но полезные дефолты.
SHEETS_TZ=Europe/Moscow
DEBOUNCE_WINDOW_MINUTES=30
```

Как сгенерировать безопасный секрет:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

---

## 6) Готовый `requirements.txt` (пример)

Обычно в проекте уже есть `requirements.txt`.  
Ниже минимально важные пакеты для backend webhook + PostgreSQL:

```txt
fastapi
uvicorn[standard]
sqlalchemy
psycopg[binary]==3.3.2
python-dotenv
```

Если у вас в репозитории `requirements.txt` уже заполнен, используйте его как source of truth:

```bash
cd /opt/MB_LK_leads
source venv/bin/activate
pip install -r requirements.txt
```

---

## 7) Готовый systemd unit (под вставку)

Файл: `/etc/systemd/system/mb-lk-webhook.service`

```ini
[Unit]
Description=MB_LK Leads Webhook Backend
After=network.target

[Service]
User=root
WorkingDirectory=/opt/MB_LK_leads
ExecStart=/opt/MB_LK_leads/venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Применение:

```bash
systemctl daemon-reload
systemctl enable mb-lk-webhook
systemctl start mb-lk-webhook
systemctl status mb-lk-webhook --no-pager
```

Логи:

```bash
journalctl -u mb-lk-webhook -f
```

---

## 8) Готовый nginx-конфиг (под вставку)

Файл: `/etc/nginx/sites-available/tech-leads.example.ru`

```nginx
server {
    listen 80;
    server_name tech-leads.example.ru;

    # Health-check для проверки backend через nginx
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Webhook endpoint (секрет должен совпадать с WEBHOOK_SECRET из .env)
    location /api/provider-test/CHANGE_ME_VERY_LONG_RANDOM_SECRET {
        proxy_pass http://127.0.0.1:8000/api/provider-test/CHANGE_ME_VERY_LONG_RANDOM_SECRET;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Включение сайта:

```bash
ln -sf /etc/nginx/sites-available/tech-leads.example.ru /etc/nginx/sites-enabled/tech-leads.example.ru
nginx -t
systemctl reload nginx
```

---

## 9) Проверка end-to-end

Проверка backend:

```bash
curl http://tech-leads.example.ru/health
```

Тест webhook:

```bash
curl -X POST "http://tech-leads.example.ru/api/provider-test/CHANGE_ME_VERY_LONG_RANDOM_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"vid":"smoke-001","page":"B1_TestSource","phones":["79990000000"],"time":1730000000,"subdomain":"test"}'
```

Ожидаемо:

- Ответ JSON с `ok: true`.
- В БД появляется запись в `provider_leads`.
- В `logs/provider_webhook.log` появляется запись.

---

## 10) Временный тестовый режим: `webhook_test.py`

`webhook_test.py` подходит только для проверки, что провайдер вообще достучался до вашего URL.

Запуск:

```bash
cd /opt/MB_LK_leads
source venv/bin/activate
uvicorn webhook_test:app --host 127.0.0.1 --port 8005
```

Важно:

- этот скрипт пишет входящие данные в лог;
- этот скрипт не сохраняет лиды в PostgreSQL;
- для боевого приема нужен сервис `backend.app.main:app`.

---

## 11) Чек-лист перед передачей URL провайдеру

- `systemctl status mb-lk-webhook` = active (running)
- `nginx -t` без ошибок
- домен резолвится в IP сервера
- `WEBHOOK_SECRET` сложный и не короткий
- тестовый `curl` прошел успешно

Готовый URL для провайдера:
`http://tech-leads.example.ru/api/provider-test/CHANGE_ME_VERY_LONG_RANDOM_SECRET`

После включения HTTPS замените на `https://...`.

