# MQTT setup

This project runs Mosquitto as the MQTT broker. Think of the broker as a small
message post office:

- the app publishes control messages to `app/control/{robot_code}`
- the backend subscribes to those control messages
- the backend publishes robot status to `robot/status/{robot_code}`
- the app subscribes to robot status

## What you need to configure

For local development, the only file you usually need to touch is
`backend/.env`.

The current development defaults are:

```env
MQTT_BROKER_HOST=127.0.0.1
MQTT_BROKER_PORT=1883
MQTT_USERNAME=parking_backend
MQTT_PASSWORD=parking_backend_dev
MQTT_APP_USERNAME=parking_app
MQTT_APP_PASSWORD=parking_app_dev
```

Use `MQTT_USERNAME` and `MQTT_PASSWORD` for the backend service.
Use `MQTT_APP_USERNAME` and `MQTT_APP_PASSWORD` for the mobile app or test
client.

When you run the backend inside `docker compose`, the compose file overrides
`MQTT_BROKER_HOST` to `mosquitto`, because containers talk to each other by
service name. When you run the backend directly on your computer, keep
`MQTT_BROKER_HOST=127.0.0.1`.

## Start MQTT locally

From the project root:

```powershell
docker compose up -d mosquitto
```

Mosquitto now starts with authentication enabled. The container generates a
temporary password file and ACL file from `backend/.env`.

## Permissions

The backend account can:

- read `app/control/#`
- write `robot/status/#`
- write `alarm/notify`
- write `system/broadcast`

The app account can:

- write `app/control/#`
- read `robot/status/#`
- read `alarm/notify`
- read `system/broadcast`

This prevents a random MQTT client from publishing robot control commands
without a username and password.

## Quick test

Open two terminals in the `backend` directory.

Terminal 1:

```powershell
python scripts/test_mqtt.py subscribe-status
```

Terminal 2:

```powershell
python scripts/test_mqtt.py publish-status
python scripts/test_mqtt.py publish-control
```

If authentication is wrong, the client will fail to connect or publish. Check
that the values in `backend/.env` match the values used by the app or test
client.

## Before real robot deployment

Change the default development passwords before using the robot on a shared
network:

```env
MQTT_PASSWORD=use-a-strong-backend-password
MQTT_APP_PASSWORD=use-a-strong-app-password
```

Then restart Mosquitto and the backend:

```powershell
docker compose up -d --force-recreate mosquitto backend
```
