# The site plus the weekly pipeline. serve.py serves web/ and the episodes on the volume; the
# in-container cron (supercronic) writes, renders, and publishes one episode every Tuesday at 5am
# Pacific. Locally rendered episodes ride along in seed/ and are copied onto the volume at boot.
#
# Build context is dist/ only. Run `python3 scripts/stage_site.py` before `fly deploy`.
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64
RUN curl -fsSL "$SUPERCRONIC_URL" -o /usr/local/bin/supercronic && chmod +x /usr/local/bin/supercronic
# The only two dependencies: the Claude SDK for the writer, Pillow for episode art.
RUN pip install --no-cache-dir anthropic==0.125.0 pillow==12.3.0
COPY dist/ ./
ENV HOST=0.0.0.0 PORT=8080 PYTHONUNBUFFERED=1 EPISODES_DIR=/data/episodes
EXPOSE 8080
ENTRYPOINT ["./docker-entrypoint.sh"]
