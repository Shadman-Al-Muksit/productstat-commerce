FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir -r requirements.lock.txt && useradd --create-home app
COPY backend /app
RUN mkdir -p /app/private_media /app/staticfiles && chown -R app:app /app
USER app
EXPOSE 8001
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8001", "--workers", "4", "--threads", "4", "--timeout", "60", "--error-logfile", "-"]
