FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend

ENV REFIND_DATABASE_PATH=/data/refind.db
ENV REFIND_UPLOAD_DIR=/data/uploads
ENV REFIND_CORS_ORIGINS=http://localhost:5173

RUN mkdir -p /data/uploads
RUN useradd --create-home --uid 10001 refind && chown -R refind:refind /app /data

USER refind

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD sh -c "python -c \"import urllib.request, os; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8001') + '/health')\""

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8001}"]
