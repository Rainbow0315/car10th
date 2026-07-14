#!/bin/sh
set -eu

: "${MQTT_BACKEND_USERNAME:=${MQTT_USERNAME:-parking_backend}}"
: "${MQTT_BACKEND_PASSWORD:=${MQTT_PASSWORD:-parking_backend_dev}}"
: "${MQTT_APP_USERNAME:=parking_app}"
: "${MQTT_APP_PASSWORD:=parking_app_dev}"
: "${MQTT_ROBOT_USERNAME:=parking_robot}"
: "${MQTT_ROBOT_PASSWORD:=parking_robot_dev}"

if [ "$MQTT_BACKEND_USERNAME" = "$MQTT_APP_USERNAME" ]; then
  echo "MQTT_BACKEND_USERNAME and MQTT_APP_USERNAME must be different." >&2
  exit 1
fi

rm -f /tmp/mosquitto_passwd /tmp/mosquitto_acl

mosquitto_passwd -b -c /tmp/mosquitto_passwd "$MQTT_BACKEND_USERNAME" "$MQTT_BACKEND_PASSWORD"
mosquitto_passwd -b /tmp/mosquitto_passwd "$MQTT_APP_USERNAME" "$MQTT_APP_PASSWORD"
mosquitto_passwd -b /tmp/mosquitto_passwd "$MQTT_ROBOT_USERNAME" "$MQTT_ROBOT_PASSWORD"
chown mosquitto:mosquitto /tmp/mosquitto_passwd
chmod 600 /tmp/mosquitto_passwd

cat > /tmp/mosquitto_acl <<EOF
user $MQTT_BACKEND_USERNAME
topic read app/control/#
topic read robot/#
topic write fleet/#
topic write robot/status/#
topic write alarm/notify
topic write system/broadcast

user $MQTT_APP_USERNAME
topic write app/control/#
topic read robot/status/#
topic read alarm/notify
topic read system/broadcast

user $MQTT_ROBOT_USERNAME
topic write robot/#
topic read fleet/command/#
topic read fleet/task/#
topic read fleet/broadcast
EOF
chown mosquitto:mosquitto /tmp/mosquitto_acl
chmod 600 /tmp/mosquitto_acl

exec mosquitto -c /mosquitto/config/mosquitto.conf
