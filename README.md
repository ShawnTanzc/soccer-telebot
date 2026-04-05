# Soccer Group Telegram Bot

A Telegram bot for managing soccer group events, tracking payments, and sending weekly reminders.

## Features

- **Event Management**: Create, view, join, and leave events
- **Payment Tracking**: Track who has paid and who hasn't for each event
- **Weekly Reminders**: Set up recurring reminders (e.g., "Book the court!")

## Setup

### 1. Create a Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow the prompts
3. Copy the bot token you receive

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add your bot token:

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

### 4. Run the Bot

```bash
python bot.py
```

## Commands

### Event Commands

| Command | Description |
|---------|-------------|
| `/newevent` | Create a new event (guided wizard) |
| `/events` | List all upcoming events |
| `/event <id>` | View details of a specific event |
| `/join <id>` | Join an event |
| `/leave <id>` | Leave an event |
| `/deleteevent <id>` | Delete an event |

### Payment Commands

| Command | Description |
|---------|-------------|
| `/paid <id>` | Mark yourself as paid for an event |
| `/unpaid <id>` | Mark yourself as unpaid |
| `/setpaid <id> @user` | Mark another user as paid |
| `/setunpaid <id> @user` | Mark another user as unpaid |
| `/payments <id>` | View payment status for an event |

### Reminder Commands

| Command | Description |
|---------|-------------|
| `/newreminder` | Set up a weekly reminder |
| `/reminders` | List all active reminders |
| `/deletereminder <id>` | Delete a reminder |

## Example Usage

### Creating an Event

```
You: /newevent
Bot: What's the name of the event?
You: Saturday Soccer
Bot: What date is the event? (YYYY-MM-DD)
You: 2024-03-16
Bot: What time does it start? (HH:MM)
You: 19:00
Bot: What's the location?
You: Sports Complex Court 3
Bot: Maximum number of players?
You: 14

Bot: ✅ Event created!
     Saturday Soccer
     📅 2024-03-16 at 19:00
     📍 Sports Complex Court 3
     👥 Max players: 14
     Event ID: 1
```

### Setting Up a Weekly Reminder

```
You: /newreminder
Bot: Which day of the week? [buttons appear]
You: [click Wednesday]
Bot: What time? (HH:MM)
You: 10:00
Bot: What message?
You: Don't forget to book the court for Saturday!

Bot: ✅ Reminder set!
     📅 Every Wednesday at 10:00
     💬 "Don't forget to book the court for Saturday!"
```

## Data Storage

All data is stored locally in `soccer_bot.db` (SQLite database). The database is created automatically on first run.
