FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN python -m pip install --no-cache-dir -r requirements-dev.txt

COPY manage.py ./
COPY config ./config
COPY gouda ./gouda

CMD ["python", "manage.py", "runlocal", "--host", "127.0.0.1", "--port", "8000"]
