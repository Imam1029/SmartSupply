#!/usr/bin/env bash
# Render build command -- installs deps, collects static files for
# WhiteNoise to serve, and applies migrations. Runs on every deploy.
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

python manage.py create_admin
