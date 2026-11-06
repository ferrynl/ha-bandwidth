FROM python:3.13-alpine
RUN apk add --no-cache iproute2 tzdata
WORKDIR /app
COPY monitor.py destinations.py dashboard.html dashboard.js dashboard.css ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "monitor.py"]
