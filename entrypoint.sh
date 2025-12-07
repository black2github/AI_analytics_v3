#!/bin/bash
set -e

echo "[ENTRYPOINT] Запуск контейнера с WireGuard..."

# Проверка наличия конфигурационного файла
if [ -f /etc/wireguard/wg0.conf ]; then
  echo "[WIREGUARD] Найден конфигурационный файл. Запускаем WireGuard..."
  chmod 600 /etc/wireguard/wg0.conf
  wg-quick up wg0

  if ip link show wg0 >/dev/null 2>&1; then
    echo "[WIREGUARD] Интерфейс wg0 успешно активирован."
  else
    echo "[WIREGUARD][ОШИБКА] Не удалось активировать интерфейс wg0."
    exit 1
  fi
else
  echo "[WIREGUARD][ПРЕДУПРЕЖДЕНИЕ] Конфигурационный файл WireGuard (/etc/wireguard/wg0.conf) не найден. Продолжаем без туннеля."
fi

echo "[APP] Запуск FastAPI сервиса..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
