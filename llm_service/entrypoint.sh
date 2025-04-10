#!/bin/sh
set -e

# Устанавливаем переменную окружения, чтобы сервер Ollama слушал на всех интерфейсах
export OLLAMA_HOST="http://0.0.0.0:11434"

# Запускаем Ollama сервер в фоновом режиме
echo "Запуск сервера Ollama..."
ollama serve &
OLLAMA_PID=$!

# Ждем, пока сервер станет доступен (проверяем через curl на 0.0.0.0:11434)
echo "Ожидание запуска сервера Ollama..."
until curl -s http://0.0.0.0:11434 > /dev/null; do
    sleep 2
done

echo "Сервер Ollama запущен. Загружаем модель YandexGPT-5-Lite-8B-instruct-GGUF..."
# Выполняем pull модели
ollama pull yandex/YandexGPT-5-Lite-8B-instruct-GGUF

# Ждем завершения фонового процесса (сервера)
wait $OLLAMA_PID