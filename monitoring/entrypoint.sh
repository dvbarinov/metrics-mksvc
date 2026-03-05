#!/bin/sh
set -eu

TEMPLATE=/etc/alertmanager/alertmanager.yml.tmpl
CONFIG=/etc/alertmanager/alertmanager.yml

echo "Generating Alertmanager config from template..."

if [ ! -f "$TEMPLATE" ]; then
  echo "Template not found: $TEMPLATE"
  exit 1
fi

# Подставляем только переменные, которые реально используются
VARS=$(env | cut -d= -f1 | sed 's/^/${/;s/$/}/')

# Генерируем конфиг из шаблона
envsubst "$VARS" < "$TEMPLATE" > "$CONFIG"

echo "Config generated:"
echo "--------------------------------"
cat "$CONFIG"
echo "--------------------------------"

# Запускаем Alertmanager
exec /bin/alertmanager --config.file="$CONFIG" "$@"