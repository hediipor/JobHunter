#!/bin/bash
# Double-click this file to start JobHunter AI.
# First run installs dependencies into a local venv (~1-2 min); after that it's instant.
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "First run — setting up (this takes a minute)..."
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r backend/requirements.txt
fi

cd backend
../.venv/bin/python launcher.py
