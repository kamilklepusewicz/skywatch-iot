FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/skywatch.sqlite3

WORKDIR /opt/skywatch/backend
COPY pyproject.toml ./
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/pip python -m pip install . \
    && useradd --uid 10001 --user-group --no-create-home skywatch \
    && install -d -o skywatch -g skywatch /data
COPY --from=contracts . /opt/skywatch/shared/contracts/

USER skywatch
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
