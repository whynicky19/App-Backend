# Chatra Backend

FastAPI + SQLAlchemy бэкенд для образовательной платформы Chatra.

## Запуск

### 1. Создать виртуальное окружение и установить зависимости

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### 2. Создать файл `.env`

```bash
cp .env.example .env   # если есть шаблон
# или создать вручную:
```

Содержимое `.env`:

```env
OPENAI_API_KEY=sk-proj-...       # ключ с platform.openai.com/api-keys
SECRET_KEY=минимум-32-случайных-символа
DATABASE_URL=sqlite:///./chatra.db   # или postgresql://user:pass@host/db
APP_BASE_URL=http://localhost:8000
```

### 3. Запустить сервер

```bash
source venv/bin/activate
uvicorn main:app --reload --reload-exclude venv --host 0.0.0.0 --port 8000
```

Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)  
Health check: [http://localhost:8000/health](http://localhost:8000/health)

---

## База данных

По умолчанию используется SQLite (`chatra.db` в корне проекта) — таблицы создаются автоматически при первом запуске.

Для PostgreSQL укажите `DATABASE_URL=postgresql://user:pass@host/db`. Схемы `university` и `school` создадутся автоматически.

Если нужны миграции:

```bash
alembic upgrade head
```

---

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `OPENAI_API_KEY` | **Обязательно для AI функций** | — |
| `SECRET_KEY` | Секрет для подписи JWT | небезопасный дефолт |
| `DATABASE_URL` | SQLAlchemy строка подключения | `sqlite:///./chatra.db` |
| `APP_BASE_URL` | Базовый URL для ссылок на файлы | `http://localhost:8000` |
| `UPLOAD_DIR` | Папка для загружаемых файлов | `uploads` |
| `CORS_ORIGINS` | Разрешённые origins через запятую, или `*` | `*` |

---

## AI оценивание

Задания оцениваются через OpenAI GPT-4o-mini по умолчанию.  
Для GPT-4o измените `OPENAI_MODEL` в `services/ai_grader.py` и `routers/ai.py`.

---

## Структура проекта

```
main.py          — точка входа, FastAPI app
models.py        — SQLAlchemy модели
schemas.py       — Pydantic схемы
db.py            — настройка базы данных
deps.py          — зависимости (get_db, get_current_user)
security.py      — JWT утилиты
routers/         — эндпоинты (auth, users, classes, ai, ...)
crud/            — операции с БД
services/        — бизнес-логика (ai_grader, deadline_checker, ...)
parsers/         — парсинг файлов (PDF, DOCX, OCR)
websocket.py     — WebSocket чат
migrations/      — Alembic миграции
uploads/         — загруженные файлы
```
source venv/bin/activate 


uvicorn main:app --host 0.0.0.0 --port 8000