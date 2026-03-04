# WR_wh_leads — краткая инструкция

Проект принимает webhook-лиды, сохраняет их в PostgreSQL, отправляет уведомления на email и выгружает данные в Google Sheets.

## Архитектура

- **nginx** принимает запросы на `http://wrmb-wh.webtm.ru`
- **wr_wh_leads.service** запускает `uvicorn app.main:app` на `127.0.0.1:8000`
- **Endpoint:** `POST http://wrmb-wh.webtm.ru/api/provider-test/<WEBHOOK_SECRET>`
- Лиды сохраняются в таблицу `provider_leads` (дедупликация по `lead_uid`)
- Фоновый воркер отправляет письма на `TO_EMAIL` (claim-механика, ретраи)
- Скрипт `export_leads_to_sheet.py` выгружает лиды в Google Sheets (cron каждые 20 мин)

---

## 1) Обновление кода на сервере

```bash
cd /opt/WR_wh_leads
git pull
source venv/bin/activate
pip install -r requirements.txt
systemctl restart wr_wh_leads
systemctl status wr_wh_leads --no-pager
```

---

## 2) Быстрая проверка

```bash
systemctl status wr_wh_leads --no-pager
systemctl status nginx --no-pager
ufw status
```

Health-check:

```bash
curl http://wrmb-wh.webtm.ru/health
```

Проверка webhook:

```bash
curl -X POST "http://wrmb-wh.webtm.ru/api/provider-test/<WEBHOOK_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"uuid":"test-123","site":"example.com"}'
```

Ожидаемый ответ:

```json
{"ok":true,"lead_id":123,"lead_state":"new"}
```

При повторной отправке с тем же `uuid`/`vid`:

```json
{"ok":true,"lead_id":123,"lead_state":"duplicate"}
```

---

## 3) Логи и БД

Логи сервиса (включая отправку писем):

```bash
journalctl -u wr_wh_leads -f
```

Webhook payload:

```bash
tail -f /opt/WR_wh_leads/logs/provider_webhook.log
```

Выгрузка в Google Sheets:

```bash
tail -f /opt/WR_wh_leads/logs/export_leads_to_sheet.log
```

Проверка БД (подготовить переменную один раз):

```bash
cd /opt/WR_wh_leads && source venv/bin/activate && set -a && source .env && set +a && export PSQL_DATABASE_URL="${DATABASE_URL/postgresql+psycopg/postgresql}"
psql "$PSQL_DATABASE_URL" -c "SELECT email_status, COUNT(*) FROM provider_leads GROUP BY email_status;"
```

Подробные SQL-команды и re-drive failed-лидов — в `docs/команды_sql_и_ретраи_почты.md`.

---

## 4) Полезные команды

Перезапуск Nginx:

```bash
nginx -t
systemctl restart nginx
```

Перезапуск приложения:

```bash
systemctl restart wr_wh_leads
```

---

## 5) API для провайдера

```text
http://wrmb-wh.webtm.ru/api/provider-test/<WEBHOOK_SECRET>
```

`<WEBHOOK_SECRET>` должен совпадать с `WEBHOOK_SECRET` в `.env`.

---

## 6) Переменные окружения

Основные (см. `.env.example`):

| Переменная | Описание |
|------------|----------|
| `DATABASE_URL` | PostgreSQL (формат `postgresql+psycopg://...`) |
| `WEBHOOK_SECRET` | Секрет для webhook |
| `YANDEX_EMAIL` | Почта-отправитель |
| `YANDEX_APP_PASSWORD` | Пароль приложения Яндекса |
| `TO_EMAIL` | Куда отправлять лиды |
| `CITY_LEADS` | Город в письме (по умолчанию Moscow) |
| `EMAIL_SEND_DELAY_SECONDS` | Пауза между письмами (рекомендуется 20–30 при rate limit) |
| `EMAIL_MAX_ATTEMPTS` | Попыток на лид (0 = отключить отправку) |
| `EMAIL_POLL_INTERVAL_SECONDS` | Интервал проверки очереди |
| `GOOGLE_CREDENTIALS_FILE` | Путь к JSON сервисного аккаунта |
| `GOOGLE_SHEET_ID` | ID таблицы для выгрузки лидов |
| `EXPORT_LEADS_LOG_PATH` | Лог скрипта выгрузки |

Временное отключение отправки писем: `EMAIL_MAX_ATTEMPTS=0` и `systemctl restart wr_wh_leads`.

---

## 7) Выгрузка в Google Sheets

Скрипт `export_leads_to_sheet.py`:

- Берёт лиды за последние 24 часа
- Пишет в лист «Месяц Год» (например «Март 2026»)
- Дедупликация по `lead_uid`, обновление статуса почты

Запуск вручную:

```bash
cd /opt/WR_wh_leads && source venv/bin/activate && python export_leads_to_sheet.py
```

Cron (каждые 20 минут):

```bash
*/20 * * * * cd /opt/WR_wh_leads && /usr/bin/flock -n /tmp/wr_wh_leads_export.lock /opt/WR_wh_leads/venv/bin/python /opt/WR_wh_leads/export_leads_to_sheet.py >/dev/null 2>&1
```

---

## 8) Утилиты

| Файл | Назначение |
|------|------------|
| `send_test_email.py` | Ручная проверка SMTP |
| `webhook_test.py` | Минимальный тестовый webhook-сервер |
| `util_table_explorer.py` | Анализ структуры Google Sheets |

---

## 9) Документация

| Файл | Содержание |
|------|------------|
| `docs/команды_sql_и_ретраи_почты.md` | SQL-команды, re-drive failed, мониторинг |
| `docs/Лимиты_почты_решение.md` | Решения при 450 rate limit |
| `docs/настройка нового сервера.md` | Деплой с нуля |
| `docs/создание_БД.md` | Создание БД PostgreSQL |
