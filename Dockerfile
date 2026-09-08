FROM python:3.11-slim

WORKDIR /app

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY run.py .

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV SPREADSHEET_ID=1oibdWWMrTXoFXozDIo4jfcukfNNJOfMbrTduzDS0Ji4

CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8000"]
