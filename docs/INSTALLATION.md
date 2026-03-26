# Installation Guide

## Prerequisites

- Python 3.11 or newer
- `pip`

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run backend

```bash
python run_api.py
```

## Run async worker (optional)

Habilita primero en entorno:

```bash
set USE_RQ=true
set REDIS_URL=redis://localhost:6379/0
```

Luego ejecuta:

```bash
python -c "from coderag.jobs.worker import run_worker; run_worker()"
```

## Run desktop UI

```bash
python run_ui.py
```

## Run tests

```bash
.venv\Scripts\python.exe -m pytest -q
```

## Supported ingestion file types

- Supported: `.md`, `.txt`, `.html`, `.htm`, `.pdf`, `.docx`, `.doc`,
  `.pptx`, `.xlsx`
- Not supported in this version: `.ppt`, `.xls`

## Cleanup local artifacts

En sesiones con politica que bloquea `Remove-Item`, usa:

```bash
.venv\Scripts\python.exe scripts/clean_artifacts.py --remove-metadata-db
```
