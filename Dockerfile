FROM node:18-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y \
    poppler-utils libmagic1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY data/ ./data/
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
