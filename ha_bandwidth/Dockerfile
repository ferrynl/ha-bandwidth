FROM python:3.13-alpine
RUN apk add --no-cache iproute2 tzdata
WORKDIR /app
COPY config.yaml monitor.py destinations.py modem.py openwrt.py storage_backup.py dashboard.html dashboard.js dashboard.css ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "monitor.py"]
