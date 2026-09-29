#!/bin/sh
# Seed the volume from the image, rebuild the site data from what is on the volume, start the
# weekly cron, then serve. Rebuilding at boot means a deploy never leaves the feed out of date
# with the episodes the cron added since the last one.
set -e
mkdir -p "${EPISODES_DIR:-/data/episodes}" /data/logs
python scripts/seed_volume.py
python scripts/build_catalog.py || echo "[entrypoint] catalog build failed"
python scripts/build_feed.py --base "${SITE_URL}" || echo "[entrypoint] feed build failed"
supercronic /app/crontab &
exec python scripts/serve.py
