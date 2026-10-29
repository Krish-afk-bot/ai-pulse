FROM python:3.12-slim
WORKDIR /app

# Dependencies first: this layer is cached unless requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run as a non-root user. /app is chowned so the app can write its SQLite file.
RUN useradd --create-home appuser && chown appuser:appuser /app
COPY --chown=appuser:appuser . .
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
