#!/bin/bash
# Run this once on your Oracle Cloud VM to set up the bot

set -e

echo "=== Soccer Bot Setup ==="

# Install dependencies
sudo apt update
sudo apt install -y python3-pip python3-venv git

# Create directory if not exists
mkdir -p ~/soccer-telebot
cd ~/soccer-telebot

# Set up Python virtual environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Prompt for bot token
echo ""
read -p "Enter your Telegram Bot Token: " BOT_TOKEN
echo "TELEGRAM_BOT_TOKEN=$BOT_TOKEN" > .env

# Install systemd service
sudo cp deploy/soccerbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable soccerbot
sudo systemctl start soccerbot

echo ""
echo "=== Setup Complete ==="
echo "Bot is now running!"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status soccerbot  - Check status"
echo "  sudo systemctl restart soccerbot - Restart bot"
echo "  sudo journalctl -u soccerbot -f  - View logs"
