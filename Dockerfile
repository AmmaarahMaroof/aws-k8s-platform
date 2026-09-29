# ---------- Stage 1: install dependencies ----------
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build
# Only the runtime requirements (no pytest in production)
COPY app/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Stage 2: the image that actually runs ----------
FROM python:3.12-slim-bookworm

# Create a non-root user to run the app
RUN useradd --create-home appuser

WORKDIR /app
RUN chown appuser:appuser /app
# Bring over the installed packages from the builder stage
COPY --from=builder /install /usr/local
# Our application code
COPY app/ ./app/

USER appuser
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]