FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY . /app/transcode/
ENV PYTHONPATH=/app

ENTRYPOINT ["python", "-m", "transcode.cli"]
