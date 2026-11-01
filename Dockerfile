# Chuẩn đóng gói Container Production (GokuMohandas/Made-With-ML)
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY simulator/ ./simulator/
COPY firmware_esp8266/ ./firmware_esp8266/
COPY mobile_app/ ./mobile_app/
COPY scripts/ ./scripts/
COPY test_audio/ ./test_audio/
COPY docs/kien_truc/ ./docs/kien_truc/

EXPOSE 8088

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/api/state', timeout=3)" || exit 1

CMD ["python", "-X", "utf8", "-m", "uvicorn", "simulator.server:app", "--host", "0.0.0.0", "--port", "8088"]
