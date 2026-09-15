#!/usr/bin/env python3
"""Run the Prediction League site locally: python run.py [--port 8000] [--reload]"""
import argparse
import os

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Run the Prediction League service")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--reload", action="store_true", help="Restart on code changes")
    args = parser.parse_args()
    print(f"Prediction League on http://localhost:{args.port}  (API docs: /docs)")
    uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
