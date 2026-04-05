#!/bin/bash
# Run this to update the bot after pushing changes

set -e

cd ~/soccer-telebot

echo "=== Updating Soccer Bot ==="

# Pull latest changes
git pull origin main

# Activate venv and update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Restart the bot (minimal downtime)
sudo systemctl restart soccerbot

echo ""
echo "=== Update Complete ==="
sudo systemctl status soccerbot --no-pager
