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

## Доступ к назначению штрафов
Администратор может разрешить отдельным сотрудникам или менеджерам назначать штрафы:
**Настройки → Выдать доступ → Назначение штрафов**, отметить сотрудников и нажать «Далее».
У выбранных в главном меню появляется кнопка «Назначить штраф» (выбор сотрудников → описание → сумма),
им приходит уведомление о выдаче или отзыве доступа. Себя и администраторов такой сотрудник оштрафовать не может.
Список хранится в `bot_settings` под ключом `fine_grantee_ids`, миграции БД не нужны.

## Что важно
- для красивого показа картинок в вебе и inline-режиме отчётов лучше сохранять `photo_public_url`
- старые отчеты без `photo_public_url` будут видны как текстовые карточки без картинки

## Структура проекта
```
core/                общий слой для бота и веб-админки
  db.py              пул соединений MySQL (bot/database.py оставлен как обёртка для старых импортов)
  clock.py           текущее время в часовом поясе приложения
  repositories/      весь SQL проекта, по модулю на таблицу: users, shifts, payroll, fines,
                     schedules, reports, catalogs, settings, reminders, admin_users, dashboard
bot/                 Telegram-бот
  handlers/admin/    админские хендлеры: reports, inline, employees, payroll, settings, shifts
  handlers/          остальные хендлеры (start, employee, reports, catalogs, commands)
  services/          бизнес-логика: расчёт опозданий, периоды, уведомления — данные берёт из core.repositories
  keyboards/ ui/ utils/
web/                 веб-админка
  routers/           HTTP-эндпоинты; SQL здесь нет — только вызовы core.repositories
  services/          помощники веба: фильтр сотрудников, Excel-выгрузка, разбор форм, ссылки на фото
  templates/ static/
scripts/             служебные скрипты, включая инициализацию БД
storage/             локально сохранённые фото отчётов и каталогов
run.py               точка входа для бота
run_web.py           точка входа для веб-админки
init_db.py           короткая точка входа для инициализации БД
```

### Где что менять
- **Новый или изменённый SQL** — только в `core/repositories/<таблица>.py`.
- **Правила расчёта** (опоздания, зарплата, напоминания) — в `bot/services/`.
- **Новый админский экран бота** — в подходящем модуле `bot/handlers/admin/`. Порядок под-роутеров
  в `bot/handlers/admin/__init__.py` важен: при совпадении фильтров aiogram выбирает первый хендлер.
