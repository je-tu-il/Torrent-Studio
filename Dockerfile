# Production Multi-Stage Python Dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY requirements*.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt || true

FROM python:3.11-slim AS runner
WORKDIR /app
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY . .
EXPOSE 8080
CMD ["python", "main.py"]
