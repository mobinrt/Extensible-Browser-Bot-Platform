FROM python:3.12.10-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
RUN groupadd --system app && useradd --system --gid app --home /srv app
COPY pyproject.toml requirements.lock ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
RUN pip install \
    --timeout 120 \
    --retries 10 \
    --no-cache-dir \
    -r requirements.lock \
    && pip install \
    --timeout 120 \
    --retries 10 \
    --no-cache-dir \
    --no-deps \
    --no-build-isolation \
    .
RUN mkdir -p /srv/diagnostics && chown app:app /srv/diagnostics
USER app
EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
