#!/bin/sh
# Read a broker-owned retained system topic using the application's credentials.
set -eu
# MQTT system topics contain a literal dollar sign.
# shellcheck disable=SC2016
if [ -n "${MQTT_PASSWORD:-}" ]; then
  exec mosquitto_sub -h 127.0.0.1 -u "${MQTT_USERNAME:-gruvax-api}" \
    -P "$MQTT_PASSWORD" -t '$SYS/broker/uptime' -C 1 -W 3
fi
exec mosquitto_sub -h 127.0.0.1 -t '$SYS/broker/uptime' -C 1 -W 3
