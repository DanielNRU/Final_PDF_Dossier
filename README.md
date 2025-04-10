# Telegram Final PDF Dossier Bot

Этот проект представляет собой Telegram-бота, который принимает PDF-файлы от пользователей, обрабатывает их и возвращает результат. Бот взаимодействует с локально развернутым сервисом LLM (Large Language Model) для обработки документов.

---

## Оглавление

1. [Описание проекта](#описание-проекта)
2. [Требования](#требования)
3. [Технологический стек] (#технологический-стек)
4. [Установка](#установка)
5. [Использование](#использование)
6. [Структура проекта](#структура-проекта)
7. [Контакты](#контакты)

---

## Описание проекта

Бот позволяет пользователям отправлять PDF-файлы через Telegram. Полученные файлы обрабатываются с использованием сервиса LLM, после чего результат отправляется обратно пользователю.

---

## Требования

- **Docker** версии 20.10.0 или выше
- **Docker Compose** версии 1.27.0 или выше
- **Переменные окружения**:
  - `TELEGRAM_BOT_TOKEN`: токен для доступа к Telegram Bot API.

---

## Технологический стек

### Языки и среды
- **Python 3.10** — основной язык программирования.
- **Docker / Docker Compose** — контейнеризация и управление зависимостями.
- **Ubuntu 22.04** — базовый образ для LLM-сервиса.

### Telegram бот
- **python-telegram-bot** — создание и обработка Telegram-бота.
- **asyncio** — асинхронная обработка событий.

### Работа с PDF
- **pdfplumber** — извлечение текста из PDF-документов.
- **reportlab** — генерация новых PDF-файлов.
- **emojipy** — добавление emoji в текст.

### Работа с LLM
- **langchain-ollama** — LangChain-обёртка для взаимодействия с локальными LLM через Ollama.
- **Ollama** — запуск и управление языковыми моделями (используется YandexGPT-5-Lite).

### Утилиты и системные библиотеки
- **subprocess** — выполнение команд в shell.
- **re** — регулярные выражения для обработки текста.
- **logging** — логгирование.
- **dotenv** — работа с переменными окружения.
- **Pathlib / os** — файловые и системные операции.

---

## Установка

### Локальный запуск через Docker Compose

1. **Клонируйте репозиторий:**
   ```bash
   git clone https://github.com/danielnru/final_pdf_dossier.git
   cd compiled_dossier
   ```

2. **Создайте файл `.env` и укажите необходимые переменные окружения:**
   ```bash
   cp .env.example .env
   ```

3. **Запустите сервисы с помощью Docker Compose:**
   ```bash
   docker-compose up --build
   ```

4. **Убедитесь, что сервисы запущены корректно и бот готов к работе.**

---

## Использование

1. **Найдите бота в Telegram** по его имени пользователя.
2. **Начните взаимодействие** с ботом, отправив команду `/start`.
3. **Отправьте PDF-файл** боту для обработки.
4. **Получите обработанный файл** в ответном сообщении от бота.

---

## Структура проекта

- `llm_service/`: сервис LLM для обработки PDF-файлов.
- `telegram_bot/`: исходный код Telegram-бота.
- `downloads/`: каталог для временного хранения загружаемых и обрабатываемых файлов.
- `docker-compose.yaml`: конфигурационный файл для Docker Compose.
- `entrypoint.sh`: скрипт запуска, используемый в контейнере.
- `.env.example`: пример файла с переменными окружения.
- `.gitignore`: список файлов и папок, исключаемых из репозитория.

---

## Контакты

**Разработчик:**  
Мельник Даниил Владимирович  
- **Email:** git@danieln.ru  
- **GitHub:** [DanielNRU](https://github.com/DanielNRU)  

---