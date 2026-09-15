FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    SPREADSHEET_ID=1oibdWWMrTXoFXozDIo4jfcukfNNJOfMbrTduzDS0Ji4 \
    DATA_DIR=/app/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY run.py .

EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
