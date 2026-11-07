#!/bin/sh
# Creates a venv on first run, loads .env and starts the example bot.
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
[ -f .env ] || { echo "No .env: cp .env.example .env and set BOT_TOKEN"; exit 1; }
set -a; . ./.env; set +a
exec .venv/bin/python -u examples/bot/bot.py
