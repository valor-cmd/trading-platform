FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV DATA_DIR=/app/data

RUN mkdir -p /app/data

CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
