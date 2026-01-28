# kimi-k2-turbo-preview
# kimi-k2.5
# moonshot-v1-128k-vision-preview
# moonshot-v1-8k-vision-preview
# moonshot-v1-auto
# moonshot-v1-32k
# kimi-latest
# kimi-k2-0905-preview
# moonshot-v1-8k
# moonshot-v1-32k-vision-preview
# moonshot-v1-128k
# kimi-k2-0711-preview
# kimi-k2-thinking-turbo
# kimi-k2-thinking
# # Для максимальной глубины анализа:
# LLM_MODEL = "moonshotai/kimi-k2-thinking"
# # Для production с требованием скорости:
# LLM_MODEL = "moonshotai/kimi-k2-thinking-turbo"
# Обе модели поддерживают до 262K контекст, инструменты (tools) и вывод reasoning-цепочек

import os, sys
from openai import OpenAI

from app.config import KIMI_API_KEY

key = KIMI_API_KEY
if not key:
    sys.exit("Переменная KIMI_API_KEY пуста")

# 2. Создаём клиента
client = OpenAI(api_key=key, base_url="https://api.moonshot.ai/v1")

# 3. Запрашиваем список моделей
try:
    models = client.models.list()
    for m in models.data:
        print(m.id)
except Exception as exc:
    # Распечатаем, что именно прислал сервер
    print("Ошибка при обращении к /v1/models:")
    print(exc)
    if hasattr(exc, "response"):
        print("Тело ответа:", exc.response.text)