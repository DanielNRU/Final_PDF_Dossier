FROM python:3.10-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y build-essential git

WORKDIR /app

# Копируем файл зависимостей и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код проекта
COPY . .

# Запускаем Telegram бота
CMD ["python", "-u", "main.py"]