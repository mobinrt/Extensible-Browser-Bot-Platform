# Optional self-contained local Chrome worker, retaining the project's Python pin.
FROM python:3.12.10-slim AS python_runtime
FROM selenium/standalone-chrome:4.51.0-20261010
USER root
COPY --from=python_runtime /usr/local /opt/python312
RUN echo /opt/python312/lib > /etc/ld.so.conf.d/bot-python312.conf && ldconfig \
    && /opt/python312/bin/python3.12 -m venv /opt/bot-venv
WORKDIR /srv
COPY pyproject.toml requirements.lock requirements-uc.lock ./
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
RUN /opt/bot-venv/bin/python -m pip install --index-url ${PIP_INDEX_URL} \
    --timeout 30 --retries 1 -r requirements-uc.lock
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN /opt/bot-venv/bin/python -m pip install --no-deps --no-build-isolation . \
    && mkdir -p /srv/diagnostics && chown -R seluser:seluser /srv \
    && install -d -o seluser -g seluser /home/seluser/.local/share/undetected_chromedriver \
    && python3 -c 'from pathlib import Path; p=Path("/etc/supervisor/conf.d/selenium.conf"); text=p.read_text(); start=text.index("[program:selenium-standalone]"); p.write_text(text[:start])'
RUN rm /etc/supervisor/conf.d/recorder.conf /etc/supervisor/conf.d/uploader.conf
COPY uc-worker.conf /etc/supervisor/conf.d/bot-worker.conf
ENV BROWSER_BACKEND=undetected-chrome CHROME_BINARY=/usr/bin/google-chrome \
    CHROMEDRIVER_BINARY=/usr/bin/chromedriver PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER seluser
# Compose starts Supervisor for the worker, Xvfb, VNC and noVNC.
