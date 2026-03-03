# WR_wh_leads — краткая инструкция

Проект принимает webhook, пишет лид в PostgreSQL и дублирует запись в лог.

Текущая схема:
- `nginx` принимает запросы на `http://wrmb-wh.webtm.ru`
- `wr_wh_leads.service` запускает `uvicorn app.main:app` на `127.0.0.1:8000`
- endpoint для провайдера: `http://wrmb-wh.webtm.ru/api/provider-test/<WEBHOOK_SECRET>`
- лиды сохраняются в таблицу `provider_leads`

## 1) Если изменил код проекта (главные команды)

Выполнять на сервере:

```bash
cd /opt/WR_wh_leads
git pull
source venv/bin/activate
pip install -r requirements.txt
systemctl restart wr_wh_leads
systemctl status wr_wh_leads --no-pager
```

## 2) Быстрая проверка

```bash
systemctl status wr_wh_leads --no-pager
systemctl status nginx --no-pager
ufw status
```

Проверка health:

```bash
curl http://wrmb-wh.webtm.ru/health
```

Проверка webhook:

```bash
curl -X POST "http://wrmb-wh.webtm.ru/api/provider-test/<WEBHOOK_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"test":"ok"}'
```

Ожидаемый ответ:

```json
{"ok":true,"lead_id":123}
```

## 3) Логи и БД

Логи сервиса:

```bash
journalctl -u wr_wh_leads -f
```

Webhook payload:

```bash
tail -f /opt/WR_wh_leads/logs/provider_webhook.log
```

Проверка записей в БД:

```bash
psql "postgresql://wr_wh_leads:<PASSWORD>@127.0.0.1:5432/wr_wh_leads_prod" \
  -c "select id, received_at, lead_uid, site from provider_leads order by id desc limit 20;"
```

## 4) Полезные команды

Перезапуск Nginx после правок конфига:

```bash
nginx -t
systemctl restart nginx
```

Перезапуск только приложения:

```bash
systemctl restart wr_wh_leads
```

## 5) Что указывать у провайдера (API ссылка)

```text
http://wrmb-wh.webtm.ru/api/provider-test/<WEBHOOK_SECRET>
```

`<WEBHOOK_SECRET>` должен точно совпадать со значением `WEBHOOK_SECRET` в файле `.env`.
