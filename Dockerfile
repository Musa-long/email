FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN mkdir -p /var/data
ENV DB_PATH=/var/data/creds.db DATA_DIR=/var/data PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
