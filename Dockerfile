FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-web.txt /app/requirements-web.txt
RUN pip install --no-cache-dir -r /app/requirements-web.txt

COPY . /app

RUN mkdir -p /app/output /app/cache

EXPOSE 8000

CMD ["uvicorn", "apps.web.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

