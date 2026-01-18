FROM python:3.10-slim

WORKDIR /app

# ============================================================================
# ЭТАП 1: Системные зависимости
# ============================================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ============================================================================
# ЭТАП 2: Python зависимости (с кэшированием слоя)
# ============================================================================
COPY requirements.txt .

# Обновляем pip
ENV PIP_DEFAULT_TIMEOUT=100
RUN pip install --no-cache-dir --upgrade pip

# КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ: Устанавливаем PyTorch CPU-only ПЕРЕД requirements.txt
RUN pip install --no-cache-dir \
    --timeout 100 \
    --retries 5 \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.7.0

# Теперь устанавливаем остальные зависимости (БЕЗ torch, он уже установлен)
RUN pip install --no-cache-dir \
    --timeout 100 \
    --retries 5 \
    -r requirements.txt

# ============================================================================
# ЭТАП 3: Копирование HuggingFace кэша
# ============================================================================
# Создаем директорию для кэша HuggingFace
RUN mkdir -p /root/.cache/huggingface

# Копируем предзагруженный кэш из Windows в образ
COPY docker_cache/huggingface /root/.cache/huggingface

# Устанавливаем права доступа
RUN chmod -R 755 /root/.cache/huggingface

# Проверяем, что кэш скопировался
RUN echo "=== HuggingFace cache contents ===" && \
    ls -lh /root/.cache/huggingface/ || echo "Cache directory empty or not found"

# ============================================================================
# ЭТАП 4: Копирование кода приложения
# ============================================================================
# Очищаем только pip кэш
RUN rm -rf /root/.cache/pip

# Копируем код приложения (эти файлы меняются чаще всего)
COPY app /app/app
COPY store /app/store
COPY page_prompt_template.txt /app/
COPY template_analysis_prompt.txt /app/

# ============================================================================
# ЭТАП 5: Настройка переменных окружения для офлайн режима
# ============================================================================
ENV TRANSFORMERS_OFFLINE=1
ENV HF_HUB_OFFLINE=1
ENV HF_HOME=/root/.cache/huggingface
ENV PYTHONPATH=/app

# ============================================================================
# ЗАПУСК
# ============================================================================
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]