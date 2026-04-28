FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
	PIP_NO_CACHE_DIR=1

USER root
WORKDIR /build

RUN apt-get update \
	&& apt-get install -y --no-install-recommends build-essential \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
COPY requirements-runtime.txt ./

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN pip install --upgrade pip setuptools wheel \
	&& pip wheel --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_DISABLE_PIP_VERSION_CHECK=1 \
	PYTHONPATH=/app/src

USER root
WORKDIR /app

RUN groupadd --system app \
	&& useradd --system --gid app --create-home app

COPY --from=builder /wheels /wheels
COPY requirements.txt ./
COPY requirements-runtime.txt ./

RUN python -m venv /opt/venv \
	&& /opt/venv/bin/pip install --upgrade pip \
	&& /opt/venv/bin/pip install --no-cache-dir /wheels/* \
	&& rm -rf /wheels

ENV PATH="/opt/venv/bin:${PATH}"

COPY src ./src
COPY .env.example ./.env.example

RUN mkdir -p /storage /storage/chromadb /storage/workspace /storage/cache \
	&& chown -R app:app /app /storage

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
	CMD python -c "import urllib.request; urllib.request.urlopen('http://0.0.0.0:8000/health', timeout=2)" || exit 1

CMD ["python", "-m", "main"]
