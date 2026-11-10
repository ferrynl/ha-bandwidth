FROM python:3.13-alpine
RUN apk add --no-cache iproute2 tzdata \
    && apk add --no-cache --virtual .zyxel-build git build-base \
    && pip install --no-cache-dir 'paho-mqtt==2.1.0' 'websocket-client==1.9.0' 'nr7101 @ git+https://github.com/zulufoxtrot/nr7101.git@v2.0.2' \
    && apk del .zyxel-build
WORKDIR /app
COPY config.yaml monitor.py live_monitor.py ha_mqtt.py ha_dashboard.py lovelace.json lovelace-legacy.json lovelace-card.js destinations.py modem.py openwrt.py storage_backup.py dashboard.html dashboard.js dashboard.css ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "monitor.py"]
