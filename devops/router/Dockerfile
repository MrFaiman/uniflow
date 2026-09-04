FROM python:3.13-slim

WORKDIR /app

COPY router/router.py /app/router.py
COPY config.py /app/config.py

CMD ["python", "-u", "router.py"]