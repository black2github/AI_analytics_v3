import requests

base_url = "http://node2.gonka.ai:8000"

# Проверим различные возможные пути
paths = [
    "/chain-api/health",
    "/chain-api/status",
    "/chain-api/v1/models",
    "/v1/models",
    "/models",
    "/chain-api/productscience/inference/models",
]

for path in paths:
    url = base_url + path
    try:
        print(f"\nПроверяем: {url}")
        response = requests.get(url, timeout=5)
        print(f"Статус: {response.status_code}")
        if response.status_code == 200:
            print("Успех! Найден рабочий эндпоинт!")
            print("Ответ:", response.text[:200])
    except Exception as e:
        print(f"Ошибка: {e}")