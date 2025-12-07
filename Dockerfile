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
# ЭТАП 2: Python зависимости
# ============================================================================
COPY requirements.txt .

# Обновляем pip и устанавливаем зависимости
ENV PIP_DEFAULT_TIMEOUT=100

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    --timeout 100 \
    --retries 5 \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# ============================================================================
# ЭТАП 3: Копирование HuggingFace кэша (КЛЮЧЕВОЕ ИЗМЕНЕНИЕ)
# ============================================================================
# Создаем директорию для кэша HuggingFace
RUN mkdir -p /root/.cache/huggingface

# Копируем предзагруженный кэш из Windows в образ
# Это позволит работать без интернета
COPY docker_cache/huggingface /root/.cache/huggingface

# ВАЖНО: Устанавливаем права доступа
RUN chmod -R 755 /root/.cache/huggingface

# Проверяем, что кэш скопировался (для отладки)
RUN echo "=== HuggingFace cache contents ===" && \
    ls -lh /root/.cache/huggingface/ || echo "Cache directory empty or not found"

# ============================================================================
# ЭТАП 4: Копирование кода приложения
# ============================================================================
# Очищаем только pip кэш (НЕ трогаем huggingface кэш!)
RUN rm -rf /root/.cache/pip

# Копируем код приложения
COPY app /app/app
COPY store /app/store
COPY page_prompt_template.txt /app/
COPY template_analysis_prompt.txt /app/

# ============================================================================
# ЭТАП 5: Настройка переменных окружения для офлайн режима
# ============================================================================
# Эти переменные заставят использовать только локальный кэш
ENV TRANSFORMERS_OFFLINE=1
ENV HF_HUB_OFFLINE=1
ENV HF_HOME=/root/.cache/huggingface

# ============================================================================
# ЗАПУСК
# ============================================================================
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]