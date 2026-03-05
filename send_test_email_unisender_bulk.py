import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Не задана переменная окружения: {name}")
    return value


def send_test_email() -> None:
    load_dotenv()

    smtp_host = get_required_env("UNIS_SMTP_HOST")
    smtp_port = int(get_required_env("UNIS_SMTP_PORT"))
    smtp_username = get_required_env("UNIS_SMTP_USERNAME")
    smtp_password = get_required_env("UNIS_SMTP_PASSWORD")
    from_email = get_required_env("UNIS_FROM_EMAIL")
    to_email = get_required_env("UNIS_TO_EMAIL")

    message = EmailMessage()
    message["From"] = from_email
    message["To"] = to_email
    # Формат письма-заявки. Источники данных:
    #   Время идентификации: время определения
    #   Имя: имя как в WR (пример: Гость #1591671762)
    #   Город: город
    #   Часовой пояс: из интеграции, по умолчанию UTC +3
    #   Телефон: через "7" (79001234567)
    #   URL: полная ссылка
    #   utm_source, utm_medium, utm_campaign, utm_content, yclid: из URL
    message["Subject"] = "Новая идентификация Гость #1594954108"
    message["X-UNIGO-SKIP-UNSUBSCRIBE"] = "1"
    message["Precedence"] = "bulk"
    message.set_content(
        "Время идентификации: 2026-03-03 10:12:03.306893\n"
        "Имя: Гость #1594954108\n"
        "Город: Moscow\n"
        "Часовой пояс: UTC +3\n"
        "Телефон: 79137596376\n"
        "URL:\n"
        "1) https://estate-tai.ru/private-beach-phuket?yclid=8410654432449527807&utm_campaign=mik_707506091&utm_content=d_d4%7C17618663950%7C5721109607%7C205721109607%7Ccom.vitastudio.mahjong%7Ccontext&utm_source=yandex&utm_medium=cpc&utm_term=---autotargeting&y_ref=\n\n"
        "utm_source: yandex\n"
        "utm_medium: cpc\n"
        "utm_campaign: mik_707506091\n"
        "utm_content: d_d4|17618663950|5721109607|205721109607|com.vitastudio.mahjong|context\n"
        "utm_term: ---autotargeting\n"
        "yclid: 8410654432449527807"
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.ehlo()
        server.starttls()  # TLS (для 587)
        server.ehlo()
        server.login(smtp_username, smtp_password)
        server.send_message(message)


if __name__ == "__main__":
    try:
        send_test_email()
        print("Письмо успешно отправлено.")
    except Exception as error:
        print("Ошибка при отправке письма:")
        print(error)
