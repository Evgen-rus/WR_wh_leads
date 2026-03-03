# WR_wh_leads — краткая инструкция

Проект принимает webhook и пишет входящие данные в лог.

Сейчас сервер работает так:
- `nginx` принимает запросы на `http://wrmb-wh.webtm.ru`
- `webhook_test.service` запускает `uvicorn` на `127.0.0.1:8000`
- endpoint для провайдера: `http://wrmb-wh.webtm.ru/api/provider-test/<WEBHOOK_SECRET>`

## 1) Если изменил код проекта (главные команды)

Выполнять на сервере:

```bash
cd /opt/WR_wh_leads
git pull
source venv/bin/activate
pip install -r requirements.txt
systemctl restart webhook_test
systemctl status webhook_test --no-pager
```

Это основной рабочий сценарий после каждого изменения в репозитории.

## 2) Быстрая проверка, что все работает

```bash
systemctl status webhook_test --no-pager
systemctl status nginx --no-pager
ufw status
```

Тестовый запрос:

```bash
curl -X POST "http://wrmb-wh.webtm.ru/api/provider-test/<WEBHOOK_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"test":"ok"}'
```

Ожидаемый ответ:

```json
{"ok":true}
```

## 3) Логи

Логи приложения:

```bash
journalctl -u webhook_test -f
```

Webhook payload:

```bash
tail -f /opt/WR_wh_leads/logs/provider_webhook.log
```

## 4) Полезные команды

Перезапуск Nginx после правок конфига:

```bash
nginx -t
systemctl restart nginx
```

Перезапуск только приложения:

```bash
systemctl restart webhook_test
```

## 5) Что указывать у провайдера (API ссылка)

```text
http://wrmb-wh.webtm.ru/api/provider-test/<WEBHOOK_SECRET>
```

`<WEBHOOK_SECRET>` должен точно совпадать со значением `WEBHOOK_SECRET` в файле `.env`.
