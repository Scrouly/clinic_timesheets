# График работы врачей

Внутренняя система для составления, согласования и утверждения графиков работы врачей.
Это первый этап: каркас проекта, вход, роли, базовый интерфейс и образец сетки графика.
Модели графиков, смен и кабинетов будут добавлены на втором этапе.

## Быстрый запуск (SQLite, для знакомства)

Нужен Python 3.12 или новее.

**Windows (PowerShell):**

```powershell
cd schedule_site
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

**Linux / macOS:**

```bash
cd schedule_site
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Откройте http://127.0.0.1:8000/ . Тестовые пользователи (пароль `demo-pass-2026`):

| Логин | Роль | Что видит |
|---|---|---|
| `admin` | Администратор | всё, включая «Образец сетки» и «Пользователи» |
| `hr` | Кадровик | все отделения, сводную, справочники |
| `head_diag` | Заведующий | только диагностическое отделение |
| `head_cons` | Заведующий | консультативные отделения |
| `viewer` | Наблюдатель | все отделения, только просмотр |

Команда `seed_demo` работает только при `DEBUG=True` и нужна лишь для проверки интерфейса.

## PostgreSQL

В `.env` укажите строку подключения:

```
DATABASE_URL=postgres://ПОЛЬЗОВАТЕЛЬ:ПАРОЛЬ@СЕРВЕР:ПОРТ/ИМЯ_БАЗЫ
```

Для рабочей версии нужен именно PostgreSQL: на втором этапе проверка пересечения смен опирается на его возможности.
Создайте для проекта отдельную базу и отдельного пользователя.

## Устройство проекта

```
config/              настройки (base, dev, prod), адреса
apps/accounts/       пользователь с ролью и списком отделений
apps/core/           отделения, меню, права, страницы, образец сетки
templates/           base.html (каркас), base_auth.html (вход), partials/, страницы
static/              css, js, шрифт Golos Text, логотип (внешних запросов нет)
```

Главные решения:

- **Своя модель пользователя с первого дня.** Заменить её в готовом проекте очень трудно.
- **Вход обязателен везде.** Включён `LoginRequiredMiddleware`; открыта только страница входа.
- **Роли:** `admin`, `hr`, `head`, `viewer`. Заведующий видит только свои отделения: ограничение накладывается на выборку данных (`DepartmentScopedMixin`), а не только на меню.
- **Меню собирается по роли** из одного списка `apps/core/navigation.py`.
- **Статика локальная.** Шрифт и иконки лежат в проекте, сайт работает без интернета.
- **Цвета статусов** повторяют легенду из текущих таблиц (составлен, внесён, на согласовании, изменения, ошибки, выходной, праздничный).

## Как добавить страницу

1. Напишите view. Для ограничения по ролям используйте `RoleRequiredMixin` с `allowed_roles`.
2. Добавьте адрес в `apps/core/urls.py` (или в `urls.py` нового приложения).
3. Добавьте строку в `NAV_ITEMS` в `apps/core/navigation.py`: подпись, имя адреса, роли, группа, иконка.
4. Шаблон начните с `{% extends "base.html" %}` и заполните блоки `page_title`, `page_lead`, `page_actions`, `content`.

Готовые части шаблонов: `partials/_field.html` (поле формы), `_empty.html` (пустое состояние),
`_pagination.html` (страницы), тег `{% status_badge "approved" %}` (плашка статуса), фильтр `|hours` (часы с запятой).

## Проверки

```
python manage.py test
python manage.py check
```

Для рабочего сервера: `python manage.py check --deploy` с настройками `config.settings.prod`.
Два оставшихся замечания про HSTS для подсетей и preload сознательно не включены: система внутренняя.



