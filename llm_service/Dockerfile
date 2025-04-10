FROM ubuntu:22.04

# Обновляем систему и устанавливаем необходимые пакеты
RUN apt-get update && apt-get install -y \
    curl \
    sudo \
    dos2unix \
    && apt-get clean

# Устанавливаем Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Копируем скрипт запуска в контейнер и конвертируем его в Unix-формат
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN dos2unix /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

# Открываем порт, который используется сервером Ollama (по умолчанию 11434)
EXPOSE 11434

# Задаем скрипт entrypoint
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]