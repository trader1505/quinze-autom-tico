FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY src ./src
COPY static ./static

ENV PYTHONPATH=/app/src
EXPOSE 8080

CMD ["python", "-m", "laps1505_bot.main"]
