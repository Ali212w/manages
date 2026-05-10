#!/usr/bin/env bash
# build.sh — Render build script
# Runs once per deploy, before the web service starts.
set -o errexit  # exit on error

echo "==> Upgrading pip"
python -m pip install --upgrade pip

echo "==> Installing Python dependencies"
pip install -r requirements.txt

echo "==> Running database migrations (if any)"
# Skip silently if no migrations folder is initialised yet
if [ -d "migrations" ]; then
  flask db upgrade || echo "WARN: flask db upgrade failed — continuing"
fi

echo "==> Build finished"
