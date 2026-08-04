# Product backend (API + worker share one image; the command differs).
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# requirements-worker.txt pulls in requirements.txt via -r, so this installs
# the API deps plus the agent stack. One image runs both the API and the
# worker (only the command differs), and the worker needs google-adk/litellm.
COPY requirements.txt requirements-worker.txt ./
RUN pip install -r requirements-worker.txt

COPY . .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
