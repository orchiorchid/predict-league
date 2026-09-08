#!/usr/bin/env python3
"""
Entry point for running the Prediction League Google Sheets Service.
Usage:
    python run.py
    python run.py --port 8080 --host 0.0.0.0
"""
import argparse
import uvicorn

def main():
    parser = argparse.ArgumentParser(description="Run the Prediction League service")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload")
    args = parser.parse_args()

    print(f"🚀 Запуск Prediction League сервиса на http://{args.host}:{args.port}")
    print("📊 Подключение к Google Sheets: 1oibdWWMrTXoFXozDIo4jfcukfNNJOfMbrTduzDS0Ji4")
    print("📖 Swagger API документация: http://localhost:8000/docs\n")
    
    uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=args.reload)

if __name__ == "__main__":
    main()
