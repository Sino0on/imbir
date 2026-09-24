FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8114

CMD sh -c "echo 'Running migrations...' && \
    python manage.py migrate && \
    echo 'Collecting static files...' && \
    python manage.py collectstatic --noinput && \
    echo 'Starting Daphne server...' && \
    exec daphne -b 0.0.0.0 -p 8114 -v 2 core.asgi:application"
