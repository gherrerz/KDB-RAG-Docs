FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN adduser --disabled-password --gecos "" appuser \
	&& mkdir -p /data \
	&& chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

CMD ["python", "run_api.py"]
