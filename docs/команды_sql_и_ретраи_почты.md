# Команды для проверки и переотправки писем

Ниже команды в формате "копировать и вставить в терминал".

## 0) Подготовка переменной подключения (выполнить 1 раз на сессию)

```bash
cd /opt/WR_wh_leads && source venv/bin/activate && set -a && source .env && set +a && export PSQL_DATABASE_URL="${DATABASE_URL/postgresql+psycopg/postgresql}"
```

## 1) Показать количество лидов по статусам

```bash
psql "$PSQL_DATABASE_URL" -c "SELECT email_status, COUNT(*) FROM provider_leads GROUP BY email_status ORDER BY email_status;"
```

## 2) Показать failed за последние 24 часа

```bash
psql "$PSQL_DATABASE_URL" -c "SELECT id, lead_uid, received_at, email_attempts, email_last_error FROM provider_leads WHERE email_status='failed' AND received_at >= NOW() - INTERVAL '24 hours' ORDER BY received_at DESC;"
```

## 3) Вернуть в очередь failed за последние 24 часа (re-drive)

```bash
psql "$PSQL_DATABASE_URL" -c "UPDATE provider_leads SET email_status='pending', email_attempts=0, email_last_error=NULL WHERE email_status='failed' AND received_at >= NOW() - INTERVAL '24 hours';"
```

## 4) Вернуть в очередь все failed (осторожно, массово)

```bash
psql "$PSQL_DATABASE_URL" -c "UPDATE provider_leads SET email_status='pending', email_attempts=0, email_last_error=NULL WHERE email_status='failed';"
```

## 5) Вернуть в очередь только failed c rate limit (450/4.2.1) за последние 24 часа

```bash
psql "$PSQL_DATABASE_URL" -c "UPDATE provider_leads SET email_status='pending', email_attempts=0, email_last_error=NULL WHERE email_status='failed' AND received_at >= NOW() - INTERVAL '24 hours' AND (email_last_error ILIKE '%rate limit%' OR email_last_error ILIKE '%4.2.1%' OR email_last_error ILIKE '% 450%');"
```

## 6) Проверить, как изменились статусы после re-drive

```bash
psql "$PSQL_DATABASE_URL" -c "SELECT email_status, COUNT(*) FROM provider_leads GROUP BY email_status ORDER BY email_status;"
```

## 7) Смотреть лог сервиса в реальном времени

```bash
sudo journalctl -u wr_wh_leads -f
```

## 8) Проверить, что сервис запущен

```bash
sudo systemctl status wr_wh_leads --no-pager
```

## 9) Перезапустить сервис (если меняли .env)

```bash
sudo systemctl restart wr_wh_leads
```

## 10) Смотреть только ошибки отправки из лог-файла проекта

```bash
cd /opt/WR_wh_leads && rg "Lead email failed|rate limit|4.2.1| 450" logs/provider_webhook.log
```
