# Генерируем конфиг из шаблона
envsubst < /etc/alertmanager/alertmanager.yml.tmpl > /etc/alertmanager/alertmanager.yml

# Запускаем Alertmanager
exec /bin/alertmanager --config.file=/etc/alertmanager/alertmanager.yml "$@"