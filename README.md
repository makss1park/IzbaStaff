# Shift Bot + Web Admin

Проект содержит Telegram-бота для учета смен и веб-админку для администраторов.

## Что умеет веб-админка
- вход по логину и паролю
- роли `superadmin` и `manager`
- дашборд в стиле CRM
- фильтры по имени сотрудника и датам
- пагинация
- графики начислений и опозданий
- экспорт в Excel
- просмотр истории всех зарплатных периодов
- редактирование сотрудников и графиков
- управление веб-админами
- просмотр отчетов, смен и настроек

## Установка
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# или .venv\\Scripts\\activate для Windows
pip install -r requirements.txt
cp .env.example .env
```

Заполни `.env`, затем инициализируй БД:
```bash
python init_db.py
# или
python scripts/init_db.py
```

## Запуск бота
```bash
python run.py
```

## Запуск веб-админки
```bash
uvicorn web.main:app --host 0.0.0.0 --port 8000
```
или
```bash
python run_web.py
```

## Первый вход
Логин и пароль первого веб-админа берутся из `.env`:
- `WEB_ADMIN_USERNAME`
- `WEB_ADMIN_PASSWORD`

## Nginx пример
```nginx
server {
    listen 80;
    server_name bot.example.com;

    location /web/static/ {
        alias /opt/shift_bot/web/static/;
    }

    location /reports/ {
        alias /opt/shift_bot/storage/reports/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Роли веб-админки
- `superadmin` — полный доступ, создание и блокировка веб-админов
- `manager` — доступ к просмотру и редактированию данных сотрудников, смен и настроек

## Что важно
- для красивого показа картинок в вебе и inline-режиме отчётов лучше сохранять `photo_public_url`
- старые отчеты без `photo_public_url` будут видны как текстовые карточки без картинки

## Структура проекта
```
bot/            Telegram-бот: handlers, services, keyboards, utils
web/            веб-админка: routers, services, templates, static
scripts/        служебные скрипты, включая инициализацию БД
storage/reports/локально сохранённые фотографии отчётов
run.py          точка входа для бота
run_web.py      точка входа для веб-админки
init_db.py      короткая точка входа для инициализации БД
```
