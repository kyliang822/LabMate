FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY worker worker
COPY scripts scripts
COPY migrations migrations
RUN useradd --uid 10001 --create-home labmate && mkdir /uploads && chown labmate /uploads
USER labmate
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
