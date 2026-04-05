import os
import asyncio
import logging
import random
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import database as db

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Conversation states
EVENT_NAME, EVENT_DATE, EVENT_TIME, EVENT_LOCATION, EVENT_MAX = range(5)
REMINDER_DAY, REMINDER_TIME, REMINDER_MESSAGE = range(5, 8)
ADD_FRIEND_NAME, REMOVE_FRIEND_NAME = range(8, 10)
EVENT_LOC_SELECT = 10
EVENT_BOOKER = 11
EVENT_BOOKER_NUMBER = 12
EVENT_COST = 13
EDIT_COST = 14

DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# Helper functions
def trigger_backup():
    """Trigger a backup to GitHub Gist."""
    try:
        if db.backup_to_gist():
            logger.info("Backup to Gist successful")
        else:
            logger.debug("Backup skipped (not configured)")
    except Exception as e:
        logger.error(f"Backup failed: {e}")


def get_display_name(user) -> str:
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    return user.first_name or user.username or "Unknown"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ Soccer Group Bot\n\n"
        "📅 EVENT COMMANDS\n"
        "/newevent - Create a new event\n"
        "/events - List upcoming events\n"
        "/event [id] - View event details\n\n"
        "💰 PAYMENT\n"
        "/paid [id] - Mark yourself as paid\n"
        "/setpaid [id] @user - Mark someone as paid\n"
        "/payments [id] - View payment status\n\n"
        "⏰ REMINDERS\n"
        "/newreminder - Set up a weekly reminder\n"
        "/reminders - List active reminders\n"
        "/deletereminder [id] - Delete a reminder\n\n"
        "⚙️ SETUP\n"
        "/setuptopics - Configure which topics to use\n\n"
        "Payment reminders are sent automatically 1 hour after match ends.\n\n"
        "/help - Show this message"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


# ============ TOPIC SETUP ============

async def setup_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show topic setup menu."""
    message = update.message or update.channel_post
    if not message:
        return
    
    chat_id = update.effective_chat.id
    settings = db.get_chat_settings(chat_id)
    
    def topic_status(topic_id):
        return f"✅ Set (ID: {topic_id})" if topic_id else "❌ Not set"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📅 Events: {topic_status(settings.get('events_topic_id'))}", callback_data="setuptopic_events")],
        [InlineKeyboardButton(f"👕 Teams: {topic_status(settings.get('teams_topic_id'))}", callback_data="setuptopic_teams")],
        [InlineKeyboardButton(f"💰 Payment: {topic_status(settings.get('payment_topic_id'))}", callback_data="setuptopic_payment")],
        [InlineKeyboardButton(f"⏰ Reminders: {topic_status(settings.get('reminder_topic_id'))}", callback_data="setuptopic_reminder")],
    ])
    
    await message.reply_text(
        "⚙️ *Topic Setup*\n\n"
        "Configure which topics to use for each feature.\n"
        "Go to the desired topic and click the button below, then click 'Use This Topic'.\n\n"
        "Current settings:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def setup_topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle topic setup selection."""
    query = update.callback_query
    topic_type = query.data.replace("setuptopic_", "")
    
    context.user_data["setup_topic_type"] = topic_type
    
    topic_names = {
        "events": "📅 Upcoming Events",
        "teams": "👕 Team Sheet", 
        "payment": "💰 Payment",
        "reminder": "⏰ Ballot Reminder"
    }
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📍 Use This Topic", callback_data="confirmtopic")],
        [InlineKeyboardButton("⬅️ Back", callback_data="setuptopics_back")]
    ])
    
    await query.answer()
    await query.edit_message_text(
        f"Setting up: *{topic_names.get(topic_type, topic_type)}*\n\n"
        f"Navigate to the topic where you want this feature, then click 'Use This Topic'.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def confirm_topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and save the topic setting."""
    query = update.callback_query
    topic_type = context.user_data.get("setup_topic_type")
    
    if not topic_type:
        await query.answer("Session expired. Please start again.", show_alert=True)
        return
    
    chat_id = update.effective_chat.id
    message_thread_id = query.message.message_thread_id if query.message.is_topic_message else None
    
    db.set_chat_topic(chat_id, topic_type, message_thread_id)
    trigger_backup()
    
    topic_names = {
        "events": "📅 Upcoming Events",
        "teams": "👕 Team Sheet",
        "payment": "💰 Payment", 
        "reminder": "⏰ Ballot Reminder"
    }
    
    if message_thread_id:
        await query.answer(f"{topic_names.get(topic_type)} will use this topic!")
    else:
        await query.answer(f"{topic_names.get(topic_type)} will use General/main chat!")
    
    # Show updated settings
    settings = db.get_chat_settings(chat_id)
    
    def topic_status(topic_id):
        return f"✅ Set (ID: {topic_id})" if topic_id else "❌ Not set"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📅 Events: {topic_status(settings.get('events_topic_id'))}", callback_data="setuptopic_events")],
        [InlineKeyboardButton(f"👕 Teams: {topic_status(settings.get('teams_topic_id'))}", callback_data="setuptopic_teams")],
        [InlineKeyboardButton(f"💰 Payment: {topic_status(settings.get('payment_topic_id'))}", callback_data="setuptopic_payment")],
        [InlineKeyboardButton(f"⏰ Reminders: {topic_status(settings.get('reminder_topic_id'))}", callback_data="setuptopic_reminder")],
    ])
    
    await query.edit_message_text(
        "⚙️ *Topic Setup*\n\n"
        "Configure which topics to use for each feature.\n"
        "Go to the desired topic and click the button below, then click 'Use This Topic'.\n\n"
        "Current settings:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def setup_topics_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Go back to topic setup menu."""
    query = update.callback_query
    chat_id = update.effective_chat.id
    settings = db.get_chat_settings(chat_id)
    
    def topic_status(topic_id):
        return f"✅ Set (ID: {topic_id})" if topic_id else "❌ Not set"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📅 Events: {topic_status(settings.get('events_topic_id'))}", callback_data="setuptopic_events")],
        [InlineKeyboardButton(f"👕 Teams: {topic_status(settings.get('teams_topic_id'))}", callback_data="setuptopic_teams")],
        [InlineKeyboardButton(f"💰 Payment: {topic_status(settings.get('payment_topic_id'))}", callback_data="setuptopic_payment")],
        [InlineKeyboardButton(f"⏰ Reminders: {topic_status(settings.get('reminder_topic_id'))}", callback_data="setuptopic_reminder")],
    ])
    
    await query.answer()
    await query.edit_message_text(
        "⚙️ *Topic Setup*\n\n"
        "Configure which topics to use for each feature.\n"
        "Go to the desired topic and click the button below, then click 'Use This Topic'.\n\n"
        "Current settings:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


# ============ EVENT CREATION CONVERSATION ============

from datetime import timedelta

def get_date_keyboard(prefix="date_", cancel_data="cancel_event"):
    """Generate buttons for the next 14 days."""
    today = datetime.now()
    buttons = []
    row = []
    for i in range(14):
        date = today + timedelta(days=i)
        day_name = date.strftime("%a")
        date_str = date.strftime("%Y-%m-%d")
        display = date.strftime("%d %b") + f" ({day_name})"
        row.append(InlineKeyboardButton(display, callback_data=f"{prefix}{date_str}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=cancel_data)])
    return InlineKeyboardMarkup(buttons)


def get_time_keyboard(prefix="time_", cancel_data="cancel_event"):
    """Generate buttons for time slots."""
    times = [
        ("7-9 AM", "07:00-09:00"),
        ("9-11 AM", "09:00-11:00"),
        ("11AM-1PM", "11:00-13:00"),
        ("1-3 PM", "13:00-15:00"),
        ("3-5 PM", "15:00-17:00"),
        ("5-7 PM", "17:00-19:00"),
        ("7-9 PM", "19:00-21:00"),
    ]
    buttons = []
    for display, value in times:
        buttons.append([InlineKeyboardButton(display, callback_data=f"{prefix}{value}")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=cancel_data)])
    return InlineKeyboardMarkup(buttons)


def get_location_keyboard(prefix="loc_", cancel_data="cancel_event"):
    """Generate buttons for locations."""
    locations = [
        ("ActiveSG Sport Park @ Teck Ghee", "teckghee"),
        ("Bishan Clubhouse", "bishan"),
        ("Pasir Ris 5-a-Side Soccer Field", "pasirris"),
    ]
    buttons = []
    for display, value in locations:
        buttons.append([InlineKeyboardButton(display, callback_data=f"{prefix}{value}")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=cancel_data)])
    return InlineKeyboardMarkup(buttons)


LOCATIONS = {
    "teckghee": "ActiveSG Sport Park @ Teck Ghee",
    "bishan": "Bishan Clubhouse",
    "pasirris": "Pasir Ris 5-a-Side Soccer Field",
}


def get_max_players_keyboard():
    """Generate buttons for max players."""
    buttons = [
        [InlineKeyboardButton("15 players", callback_data="max_15"),
         InlineKeyboardButton("18 players", callback_data="max_18")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_event")]
    ]
    return InlineKeyboardMarkup(buttons)


async def new_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.channel_post
    if not message:
        return ConversationHandler.END
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id if update.effective_user else None
    
    # Check if this is a group/channel or private chat
    is_private = update.effective_chat.type == "private"
    
    if is_private:
        # Already in private chat, continue with event creation
        # Check if we have a target group stored
        if "target_chat_id" not in context.user_data:
            await message.reply_text(
                "⚠️ Please start event creation from your group chat using /newevent.\n"
                "I'll then message you privately to complete the setup."
            )
            return ConversationHandler.END
    else:
        # In group - check if we're in the correct topic
        settings = db.get_chat_settings(chat_id)
        events_topic_id = settings.get("events_topic_id")
        
        if events_topic_id is not None:
            current_topic_id = message.message_thread_id if hasattr(message, 'message_thread_id') and message.is_topic_message else None
            if current_topic_id != events_topic_id:
                await message.reply_text(
                    "⚠️ Events can only be created in the Upcoming Events topic.\n"
                    "Please go to that topic and try again."
                )
                return ConversationHandler.END
        
        # Store target chat info for posting later
        context.user_data["target_chat_id"] = chat_id
        context.user_data["target_topic_id"] = events_topic_id
        
        # Try to send private message
        if user_id:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⚽ Let's create a new event!\n\nSelect a date:",
                    reply_markup=get_date_keyboard()
                )
                await message.reply_text(
                    "📩 I've sent you a private message to set up the event.\n"
                    "Please check your DMs!"
                )
                return EVENT_DATE
            except Exception:
                # User hasn't started private chat with bot
                await message.reply_text(
                    "⚠️ I can't message you privately.\n\n"
                    "Please start a chat with me first by clicking @YourBotUsername and pressing START, "
                    "then try /newevent again.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💬 Start Private Chat", url=f"https://t.me/{(await context.bot.get_me()).username}")]
                    ])
                )
                return ConversationHandler.END
        
        # Fallback: do it in group
        await message.reply_text(
            "⚽ Let's create a new event!\n\nSelect a date:",
            reply_markup=get_date_keyboard()
        )
        return EVENT_DATE
    
    # Private chat with target set
    await message.reply_text(
        "⚽ Let's create a new event!\n\nSelect a date:",
        reply_markup=get_date_keyboard()
    )
    return EVENT_DATE


async def event_date_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_event":
        await query.edit_message_text("Cancelled.")
        context.user_data.clear()
        return ConversationHandler.END
    
    date_str = query.data.replace("date_", "")
    context.user_data["event_date"] = date_str
    
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    display_date = date_obj.strftime("%A, %d %B %Y")
    
    await query.edit_message_text(
        f"📅 Date: {display_date}\n\nSelect a time:",
        reply_markup=get_time_keyboard()
    )
    return EVENT_TIME


async def event_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_event":
        await query.edit_message_text("Cancelled.")
        context.user_data.clear()
        return ConversationHandler.END
    
    time_str = query.data.replace("time_", "")
    context.user_data["event_time"] = time_str
    
    date_obj = datetime.strptime(context.user_data["event_date"], "%Y-%m-%d")
    display_date = date_obj.strftime("%A, %d %B")
    
    await query.edit_message_text(
        f"📅 Date: {display_date}\n🕐 Time: {time_str.replace('-', ' - ')}\n\nSelect location:",
        reply_markup=get_location_keyboard()
    )
    return EVENT_LOC_SELECT


async def event_location_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_event":
        await query.edit_message_text("Cancelled.")
        context.user_data.clear()
        return ConversationHandler.END
    
    loc_key = query.data.replace("loc_", "")
    context.user_data["event_location"] = LOCATIONS.get(loc_key, "")
    
    date_obj = datetime.strptime(context.user_data["event_date"], "%Y-%m-%d")
    display_date = date_obj.strftime("%A, %d %B")
    
    await query.edit_message_text(
        f"📅 Date: {display_date}\n🕐 Time: {context.user_data['event_time'].replace('-', ' - ')}\n📍 Location: {context.user_data['event_location']}\n\nSelect max players:",
        reply_markup=get_max_players_keyboard()
    )
    return EVENT_MAX


async def event_max_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_event":
        await query.edit_message_text("Cancelled.")
        context.user_data.clear()
        return ConversationHandler.END
    
    max_players = int(query.data.replace("max_", ""))
    context.user_data["max_players"] = max_players
    
    date_obj = datetime.strptime(context.user_data["event_date"], "%Y-%m-%d")
    display_date = date_obj.strftime("%A, %d %B")
    
    await query.edit_message_text(
        f"📅 Date: {display_date}\n🕐 Time: {context.user_data['event_time'].replace('-', ' - ')}\n📍 Location: {context.user_data['event_location']}\n👥 Max: {max_players}\n\nWho is the booker? (Type their name)"
    )
    return EVENT_BOOKER


async def event_booker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.channel_post
    if not message or not message.text:
        return EVENT_BOOKER
    
    booker_name = message.text.strip()
    context.user_data["booker_name"] = booker_name
    
    await message.reply_text(
        f"Booker: {booker_name}\n\nWhat's the booker's phone number? (for PayNow)"
    )
    return EVENT_BOOKER_NUMBER


async def event_booker_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.channel_post
    if not message or not message.text:
        return EVENT_BOOKER_NUMBER
    
    booker_number = message.text.strip()
    context.user_data["booker_number"] = booker_number
    
    await message.reply_text(
        "What's the total cost for the court booking? (e.g., 30)"
    )
    return EVENT_COST


async def event_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.channel_post
    if not message or not message.text:
        return EVENT_COST
    
    cost_text = message.text.strip().replace("$", "")
    
    try:
        total_cost = float(cost_text)
    except ValueError:
        await message.reply_text("Please enter a valid number (e.g., 30)")
        return EVENT_COST
    
    # Generate event name automatically
    date_obj = datetime.strptime(context.user_data["event_date"], "%Y-%m-%d")
    event_name = f"Soccer - {date_obj.strftime('%a %d %b')}"
    
    # Check if we have a target group (created from group, setup in DM)
    target_chat_id = context.user_data.get("target_chat_id")
    
    if target_chat_id:
        # Event was created from group, post to group
        chat_id = target_chat_id
        # Always use the configured events topic
        settings = db.get_chat_settings(chat_id)
        message_thread_id = settings.get("events_topic_id")
    else:
        # Event created directly in chat
        chat_id = update.effective_chat.id
        settings = db.get_chat_settings(chat_id)
        message_thread_id = settings.get("events_topic_id")
        if message_thread_id is None and hasattr(message, 'is_topic_message') and message.is_topic_message:
            message_thread_id = message.message_thread_id
    
    event_id = db.create_event(
        name=event_name,
        date=context.user_data["event_date"],
        time=context.user_data["event_time"],
        location=context.user_data.get("event_location", ""),
        max_players=context.user_data["max_players"],
        created_by=update.effective_user.id if update.effective_user else 0,
        chat_id=chat_id,
        booker_name=context.user_data["booker_name"],
        booker_number=context.user_data["booker_number"],
        total_cost=total_cost,
        message_thread_id=message_thread_id
    )
    
    display_date = date_obj.strftime("%A, %d %B %Y")
    
    event_message = (
        f"✅ Event created!\n\n"
        f"⚽ {event_name}\n"
        f"📅 {display_date}\n"
        f"🕐 {context.user_data['event_time'].replace('-', ' - ')}\n"
        f"📍 {context.user_data.get('event_location', 'TBD')}\n"
        f"🧾 Booker: {context.user_data['booker_name']} ({context.user_data['booker_number']})\n"
        f"💰 Total cost: ${total_cost:.2f}\n"
        f"👥 0/{context.user_data['max_players']} players"
    )
    
    if target_chat_id:
        # Post to group and confirm in DM
        try:
            await context.bot.send_message(
                chat_id=target_chat_id,
                text=event_message,
                reply_markup=get_event_keyboard(event_id),
                message_thread_id=message_thread_id
            )
            await message.reply_text("✅ Event posted to the group!")
        except Exception as e:
            logger.error(f"Failed to post event to group: {e}")
            await message.reply_text(
                f"⚠️ Event created (ID: {event_id}) but failed to post to group.\n"
                f"Error: {e}\n\n"
                f"You can view it with /event {event_id}"
            )
    else:
        # Reply directly
        await message.reply_text(
            event_message,
            reply_markup=get_event_keyboard(event_id)
        )
    
    context.user_data.clear()
    trigger_backup()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


# ============ EVENT COMMANDS ============

async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events = db.get_upcoming_events()
    if not events:
        await update.message.reply_text("No upcoming events.")
        return

    message = "📅 *Upcoming Events:*\n\n"
    for event in events:
        participants = db.get_participants(event["id"])
        message += (
            f"*{event['id']}. {event['name']}*\n"
            f"   📅 {event['date']} at {event['time']}\n"
            f"   📍 {event['location'] or 'TBD'}\n"
            f"   👥 {len(participants)}/{event['max_players']} players\n\n"
        )
    await update.message.reply_text(message, parse_mode="Markdown")


async def view_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /event <event_id>")
        return

    try:
        event_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid event ID.")
        return

    event = db.get_event(event_id)
    if not event:
        await update.message.reply_text("Event not found.")
        return

    participants = db.get_participants(event_id)
    
    message = (
        f"⚽ *{event['name']}*\n\n"
        f"📅 Date: {event['date']}\n"
        f"🕐 Time: {event['time']}\n"
        f"📍 Location: {event['location'] or 'TBD'}\n"
        f"👥 Players: {len(participants)}/{event['max_players']}\n\n"
    )

    if participants:
        message += "*Participants:*\n"
        for i, p in enumerate(participants, 1):
            status = "✅" if p["paid"] else "❌"
            name = p["display_name"] or p["username"] or "Unknown"
            message += f"{i}. {name} {status}\n"
    else:
        message += "_No participants yet_\n"

    await update.message.reply_text(message, parse_mode="Markdown", reply_markup=get_event_keyboard(event_id))


# ============ INLINE BUTTON HANDLERS ============

def get_event_keyboard(event_id: int):
    """Generate inline keyboard for an event (no payment button)."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add", callback_data=f"add_{event_id}"),
         InlineKeyboardButton("➖ Remove", callback_data=f"remove_{event_id}")],
        [InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{event_id}"),
         InlineKeyboardButton("🎲 Generate Teams", callback_data=f"teams_{event_id}")],
        [InlineKeyboardButton("📋 Refresh", callback_data=f"view_{event_id}")]
    ])


def get_payment_keyboard(event_id: int):
    """Generate inline keyboard for payment reminders."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Mark Paid", callback_data=f"paid_{event_id}")],
        [InlineKeyboardButton("📋 Refresh", callback_data=f"viewpayment_{event_id}")]
    ])


def format_payment_message(event: dict, participants: list) -> str:
    """Format payment status for display."""
    total_cost = event.get("total_cost", 0)
    num_participants = len(participants)
    
    msg = f"💰 *Payment Status*\n\n⚽ {event['name']}\n"
    
    if total_cost > 0 and num_participants > 0:
        per_person = total_cost / num_participants
        msg += f"💵 ${total_cost:.2f} ÷ {num_participants} = *${per_person:.2f} per person*\n"
    
    if event.get("booker_name"):
        booker_info = event['booker_name']
        if event.get("booker_number"):
            booker_info += f"\n📱 PayNow: {event['booker_number']}"
        msg += f"\n💳 Pay to: {booker_info}\n"
    
    paid = [p for p in participants if p["paid"]]
    unpaid = [p for p in participants if not p["paid"]]
    
    msg += f"\n✅ *Paid ({len(paid)}):*\n"
    if paid:
        for p in paid:
            name = p["display_name"] or p["username"] or "Unknown"
            msg += f"  • {name}\n"
    else:
        msg += "  _None yet_\n"
    
    msg += f"\n❌ *Unpaid ({len(unpaid)}):*\n"
    if unpaid:
        for p in unpaid:
            name = p["display_name"] or p["username"] or "Unknown"
            msg += f"  • {name}\n"
    else:
        msg += "  _All paid!_\n"
    
    return msg


def format_event_message(event: dict, participants: list) -> str:
    """Format event details for display."""
    date_obj = datetime.strptime(event["date"], "%Y-%m-%d")
    display_date = date_obj.strftime("%A, %d %B")
    
    # Handle time slot format (e.g., "07:00-09:00") or single time
    time_str = event["time"]
    if "-" in time_str:
        display_time = time_str.replace("-", " - ")
    else:
        time_obj = datetime.strptime(time_str, "%H:%M")
        display_time = time_obj.strftime("%I:%M %p")
    
    msg = (
        f"⚽ {event['name']}\n"
        f"📅 {display_date}\n"
        f"🕐 {display_time}\n"
    )
    
    if event.get("location"):
        msg += f"📍 {event['location']}\n"
    
    if event.get("booker_name"):
        booker_info = event['booker_name']
        if event.get("booker_number"):
            booker_info += f" ({event['booker_number']})"
        msg += f"🧾 Booker: {booker_info}\n"
    
    # Show cost info
    total_cost = event.get("total_cost", 0)
    if total_cost > 0 and len(participants) > 0:
        per_person = total_cost / len(participants)
        msg += f"💰 ${total_cost:.2f} ÷ {len(participants)} = ${per_person:.2f}/person\n"
    elif total_cost > 0:
        msg += f"💰 Total: ${total_cost:.2f}\n"
    
    msg += f"👥 {len(participants)}/{event['max_players']} players\n"
    
    if participants:
        msg += "\n"
        for i, p in enumerate(participants, 1):
            status = "💰" if p["paid"] else "❌💰"
            name = p["display_name"] or p["username"] or "Unknown"
            msg += f"{i}. {name} {status}\n"
    
    return msg


async def add_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    event_id = int(query.data.replace("add_", ""))
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    participants = db.get_participants(event_id)
    if len(participants) >= event["max_players"]:
        await query.answer("Event is full!", show_alert=True)
        return
    
    context.user_data["add_event_id"] = event_id
    await query.answer()
    await query.message.reply_text(
        "Type the name(s) to add:\n\n"
        "💡 Tip: Use commas to add multiple people\n"
        "Example: John, Mary, Tom\n\n"
        "(or /cancel to cancel)"
    )
    return ADD_FRIEND_NAME


async def add_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_text = update.message.text.strip()
    event_id = context.user_data.get("add_event_id")
    
    if not event_id:
        await update.message.reply_text("Something went wrong. Please try again.")
        return ConversationHandler.END
    
    event = db.get_event(event_id)
    if not event:
        await update.message.reply_text("Event not found.")
        context.user_data.clear()
        return ConversationHandler.END
    
    # Split by comma and clean up names
    names = [name.strip() for name in input_text.split(",") if name.strip()]
    
    if not names:
        await update.message.reply_text("Please enter at least one name.")
        return ADD_FRIEND_NAME
    
    participants = db.get_participants(event_id)
    spots_left = event["max_players"] - len(participants)
    
    if spots_left <= 0:
        await update.message.reply_text("Event is full!")
        context.user_data.clear()
        return ConversationHandler.END
    
    # Add as many as we can
    added = []
    skipped = []
    
    for name in names:
        if len(added) >= spots_left:
            skipped.append(name)
            continue
        
        success = db.add_guest(event_id, name, update.effective_user.id)
        if success:
            added.append(name)
        else:
            skipped.append(name)
    
    # Build response message
    if added:
        participants = db.get_participants(event_id)
        response = f"✅ Added {len(added)} player(s): {', '.join(added)}"
        if skipped:
            response += f"\n⚠️ Skipped (event full or error): {', '.join(skipped)}"
        response += "\n\n" + format_event_message(event, participants)
        await update.message.reply_text(
            response,
            reply_markup=get_event_keyboard(event_id)
        )
        trigger_backup()
    else:
        await update.message.reply_text("Failed to add anyone. Please try again.")
    
    context.user_data.clear()
    return ConversationHandler.END


async def remove_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    event_id = int(query.data.replace("remove_", ""))
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    participants = db.get_participants(event_id)
    
    if not participants:
        await query.answer("No one to remove!", show_alert=True)
        return
    
    # Show buttons for each participant
    buttons = []
    for p in participants:
        name = p["display_name"] or p["username"] or "Unknown"
        buttons.append([InlineKeyboardButton(
            f"❌ {name}", 
            callback_data=f"rm_{event_id}_{p['user_id']}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"view_{event_id}")])
    
    await query.answer()
    await query.edit_message_text(
        "Select who to remove:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def remove_person_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Format: rm_{event_id}_{user_id}
    parts = query.data.split("_")
    event_id = int(parts[1])
    user_id = int(parts[2])
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    success = db.remove_participant(event_id, user_id)
    
    if success:
        await query.answer("Removed!")
        participants = db.get_participants(event_id)
        await query.edit_message_text(
            format_event_message(event, participants),
            reply_markup=get_event_keyboard(event_id)
        )
        trigger_backup()
    else:
        await query.answer("Failed to remove.", show_alert=True)


async def paid_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    event_id = int(query.data.replace("paid_", ""))
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    # Show list of participants to mark as paid (with checkboxes)
    participants = db.get_participants(event_id)
    unpaid = [p for p in participants if not p["paid"]]
    
    if not unpaid:
        await query.answer("Everyone has paid!", show_alert=True)
        return
    
    # Initialize selection if not exists
    if "paid_selection" not in context.user_data:
        context.user_data["paid_selection"] = set()
    
    await query.answer()
    await show_paid_selection(query, event_id, context)


async def show_paid_selection(query, event_id: int, context):
    """Show the payment selection screen with checkboxes."""
    event = db.get_event(event_id)
    participants = db.get_participants(event_id)
    unpaid = [p for p in participants if not p["paid"]]
    
    selected = context.user_data.get("paid_selection", set())
    
    buttons = []
    for p in unpaid:
        name = p["display_name"] or p["username"] or "Unknown"
        user_id = p["user_id"]
        checkbox = "✅" if user_id in selected else "⬜"
        buttons.append([InlineKeyboardButton(
            f"{checkbox} {name}", 
            callback_data=f"togglepaid_{event_id}_{user_id}"
        )])
    
    # Add confirm and back buttons
    if selected:
        buttons.append([InlineKeyboardButton(f"💰 Confirm ({len(selected)} selected)", callback_data=f"confirmpaid_{event_id}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"cancelpaid_{event_id}")])
    
    await query.edit_message_text(
        "Select who paid (tap to toggle):",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def toggle_paid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Format: togglepaid_{event_id}_{user_id}
    parts = query.data.split("_")
    event_id = int(parts[1])
    user_id = int(parts[2])
    
    # Toggle selection
    if "paid_selection" not in context.user_data:
        context.user_data["paid_selection"] = set()
    
    if user_id in context.user_data["paid_selection"]:
        context.user_data["paid_selection"].remove(user_id)
    else:
        context.user_data["paid_selection"].add(user_id)
    
    await query.answer()
    await show_paid_selection(query, event_id, context)


async def confirm_paid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Format: confirmpaid_{event_id}
    event_id = int(query.data.replace("confirmpaid_", ""))
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    selected = context.user_data.get("paid_selection", set())
    
    if not selected:
        await query.answer("No one selected!", show_alert=True)
        return
    
    # Mark all selected as paid
    for user_id in selected:
        db.set_payment_status(event_id, user_id, True)
    
    count = len(selected)
    context.user_data["paid_selection"] = set()
    
    await query.answer(f"Marked {count} as paid!")
    trigger_backup()
    
    # Check if all paid - if so, delete event
    if db.check_and_delete_fully_paid_event(event_id):
        await query.edit_message_text(
            f"✅ All payments complete for {event['name']}!\n\nEvent has been archived. Thanks everyone!"
        )
        trigger_backup()
    else:
        participants = db.get_participants(event_id)
        await query.edit_message_text(
            format_payment_message(event, participants),
            reply_markup=get_payment_keyboard(event_id)
        )


async def cancel_paid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Format: cancelpaid_{event_id}
    event_id = int(query.data.replace("cancelpaid_", ""))
    
    # Clear selection
    context.user_data["paid_selection"] = set()
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    participants = db.get_participants(event_id)
    await query.answer()
    await query.edit_message_text(
        format_payment_message(event, participants),
        reply_markup=get_payment_keyboard(event_id)
    )


async def view_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    event_id = int(query.data.replace("view_", ""))
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    participants = db.get_participants(event_id)
    await query.answer()
    await query.edit_message_text(
        format_event_message(event, participants),
        reply_markup=get_event_keyboard(event_id)
    )


async def view_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh payment view."""
    query = update.callback_query
    event_id = int(query.data.replace("viewpayment_", ""))
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    participants = db.get_participants(event_id)
    await query.answer()
    await query.edit_message_text(
        format_payment_message(event, participants),
        parse_mode="Markdown",
        reply_markup=get_payment_keyboard(event_id)
    )


# ============ EDIT EVENT HANDLERS ============

def get_edit_menu_keyboard(event_id: int):
    """Generate edit menu keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Date", callback_data=f"editdate_{event_id}"),
         InlineKeyboardButton("🕐 Time", callback_data=f"edittime_{event_id}")],
        [InlineKeyboardButton("📍 Location", callback_data=f"editloc_{event_id}"),
         InlineKeyboardButton("💰 Cost", callback_data=f"editcost_{event_id}")],
        [InlineKeyboardButton("📢 Set Notification Topic", callback_data=f"edittopic_{event_id}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"view_{event_id}")]
    ])


async def edit_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show edit menu."""
    query = update.callback_query
    event_id = int(query.data.replace("edit_", ""))
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    await query.answer()
    await query.edit_message_text(
        f"✏️ *Edit Event*\n\n"
        f"⚽ {event['name']}\n"
        f"📅 Date: {event['date']}\n"
        f"🕐 Time: {event['time']}\n"
        f"📍 Location: {event.get('location', 'TBD')}\n"
        f"💰 Cost: ${event.get('total_cost', 0):.2f}\n\n"
        f"What would you like to edit?",
        parse_mode="Markdown",
        reply_markup=get_edit_menu_keyboard(event_id)
    )


async def edit_date_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show date selection for editing."""
    query = update.callback_query
    event_id = int(query.data.replace("editdate_", ""))
    
    context.user_data["editing_event_id"] = event_id
    
    await query.answer()
    await query.edit_message_text(
        "Select new date:",
        reply_markup=get_date_keyboard(prefix="newedate_", cancel_data=f"view_{event_id}")
    )


async def new_date_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new date selection."""
    query = update.callback_query
    new_date = query.data.replace("newedate_", "")
    event_id = context.user_data.get("editing_event_id")
    
    if not event_id:
        await query.answer("Error: No event selected", show_alert=True)
        return
    
    # Update event name to reflect new date
    date_obj = datetime.strptime(new_date, "%Y-%m-%d")
    new_name = f"Soccer - {date_obj.strftime('%a %d %b')}"
    
    db.update_event(event_id, date=new_date, name=new_name)
    trigger_backup()
    
    event = db.get_event(event_id)
    participants = db.get_participants(event_id)
    
    await query.answer("Date updated!")
    await query.edit_message_text(
        format_event_message(event, participants),
        reply_markup=get_event_keyboard(event_id)
    )


async def edit_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show time selection for editing."""
    query = update.callback_query
    event_id = int(query.data.replace("edittime_", ""))
    
    context.user_data["editing_event_id"] = event_id
    
    await query.answer()
    await query.edit_message_text(
        "Select new time:",
        reply_markup=get_time_keyboard(prefix="newetime_", cancel_data=f"view_{event_id}")
    )


async def new_time_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new time selection."""
    query = update.callback_query
    new_time = query.data.replace("newetime_", "")
    event_id = context.user_data.get("editing_event_id")
    
    if not event_id:
        await query.answer("Error: No event selected", show_alert=True)
        return
    
    db.update_event(event_id, time=new_time)
    trigger_backup()
    
    event = db.get_event(event_id)
    participants = db.get_participants(event_id)
    
    await query.answer("Time updated!")
    await query.edit_message_text(
        format_event_message(event, participants),
        reply_markup=get_event_keyboard(event_id)
    )


async def edit_location_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show location selection for editing."""
    query = update.callback_query
    event_id = int(query.data.replace("editloc_", ""))
    
    context.user_data["editing_event_id"] = event_id
    
    await query.answer()
    await query.edit_message_text(
        "Select new location:",
        reply_markup=get_location_keyboard(prefix="neweloc_", cancel_data=f"view_{event_id}")
    )


async def new_location_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new location selection."""
    query = update.callback_query
    loc_key = query.data.replace("neweloc_", "")
    event_id = context.user_data.get("editing_event_id")
    
    if not event_id:
        await query.answer("Error: No event selected", show_alert=True)
        return
    
    new_location = LOCATIONS.get(loc_key, loc_key)
    db.update_event(event_id, location=new_location)
    trigger_backup()
    
    event = db.get_event(event_id)
    participants = db.get_participants(event_id)
    
    await query.answer("Location updated!")
    await query.edit_message_text(
        format_event_message(event, participants),
        reply_markup=get_event_keyboard(event_id)
    )


async def edit_cost_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt for new cost."""
    query = update.callback_query
    event_id = int(query.data.replace("editcost_", ""))
    
    context.user_data["editing_event_id"] = event_id
    
    await query.answer()
    await query.edit_message_text(
        "Enter new total cost (e.g., 30):"
    )
    return EDIT_COST


async def edit_cost_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new cost input."""
    cost_text = update.message.text.strip().replace("$", "")
    event_id = context.user_data.get("editing_event_id")
    
    if not event_id:
        await update.message.reply_text("Error: No event selected")
        return ConversationHandler.END
    
    try:
        new_cost = float(cost_text)
    except ValueError:
        await update.message.reply_text("Please enter a valid number (e.g., 30)")
        return EDIT_COST
    
    db.update_event(event_id, total_cost=new_cost)
    trigger_backup()
    
    event = db.get_event(event_id)
    participants = db.get_participants(event_id)
    
    await update.message.reply_text(
        f"✅ Cost updated!\n\n" + format_event_message(event, participants),
        reply_markup=get_event_keyboard(event_id)
    )
    return ConversationHandler.END


async def edit_topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show instructions for setting notification topic."""
    query = update.callback_query
    event_id = int(query.data.replace("edittopic_", ""))
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    current_topic = event.get("message_thread_id")
    topic_status = f"Current: Topic ID {current_topic}" if current_topic else "Current: Main chat (no topic)"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📍 Use This Topic", callback_data=f"settopic_{event_id}")],
        [InlineKeyboardButton("🚫 Use Main Chat", callback_data=f"cleartopic_{event_id}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"edit_{event_id}")]
    ])
    
    await query.answer()
    await query.edit_message_text(
        f"📢 *Set Notification Topic*\n\n"
        f"⚽ {event['name']}\n"
        f"{topic_status}\n\n"
        f"To change where payment reminders are sent:\n\n"
        f"• *Use This Topic* - Send reminders to the topic where you click this button\n"
        f"• *Use Main Chat* - Send reminders to the main group chat",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def set_topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set the current topic as the notification destination."""
    query = update.callback_query
    event_id = int(query.data.replace("settopic_", ""))
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    # Get the message_thread_id from the current message context
    message_thread_id = query.message.message_thread_id if query.message.is_topic_message else None
    
    db.update_event(event_id, message_thread_id=message_thread_id)
    trigger_backup()
    
    if message_thread_id:
        await query.answer("Notifications will be sent to this topic!")
    else:
        await query.answer("Notifications will be sent to main chat!")
    
    # Return to event view
    event = db.get_event(event_id)
    participants = db.get_participants(event_id)
    await query.edit_message_text(
        format_event_message(event, participants),
        reply_markup=get_event_keyboard(event_id)
    )


async def clear_topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear the topic setting, use main chat."""
    query = update.callback_query
    event_id = int(query.data.replace("cleartopic_", ""))
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    db.update_event(event_id, message_thread_id=None)
    trigger_backup()
    
    await query.answer("Notifications will be sent to main chat!")
    
    # Return to event view
    event = db.get_event(event_id)
    participants = db.get_participants(event_id)
    await query.edit_message_text(
        format_event_message(event, participants),
        reply_markup=get_event_keyboard(event_id)
    )


# ============ TEAM GENERATION HANDLERS ============

def generate_team_options(participants: list, num_options: int = 3):
    """Generate multiple random team configurations."""
    names = [p["display_name"] or p["username"] or "Unknown" for p in participants]
    num_players = len(names)
    
    # For 15 players: 5v5v5 (3 teams)
    # For 18 players: 6v6v6 (3 teams)
    # For other numbers: split as evenly as possible into 3 teams
    team_size = num_players // 3
    remainder = num_players % 3
    
    options = []
    for _ in range(num_options):
        shuffled = names.copy()
        random.shuffle(shuffled)
        
        # Split into 3 teams
        team1_size = team_size + (1 if remainder > 0 else 0)
        team2_size = team_size + (1 if remainder > 1 else 0)
        
        team1 = shuffled[:team1_size]
        team2 = shuffled[team1_size:team1_size + team2_size]
        team3 = shuffled[team1_size + team2_size:]
        
        options.append((team1, team2, team3))
    
    return options


def format_team_option(option_num: int, teams: tuple) -> str:
    """Format a single team option for display."""
    team1, team2, team3 = teams
    
    msg = f"*Option {option_num}*\n\n"
    msg += f"🔴 *Team Red* ({len(team1)})\n"
    msg += "\n".join([f"  • {name}" for name in team1])
    msg += f"\n\n🔵 *Team Blue* ({len(team2)})\n"
    msg += "\n".join([f"  • {name}" for name in team2])
    msg += f"\n\n⚪ *Team White* ({len(team3)})\n"
    msg += "\n".join([f"  • {name}" for name in team3])
    
    return msg


async def teams_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate 3 random team options."""
    query = update.callback_query
    event_id = int(query.data.replace("teams_", ""))
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    participants = db.get_participants(event_id)
    
    if len(participants) < 6:
        await query.answer("Need at least 6 players to generate teams!", show_alert=True)
        return
    
    # Generate 3 options
    options = generate_team_options(participants, 3)
    context.user_data["team_options"] = options
    context.user_data["team_event_id"] = event_id
    
    # Show first option with navigation
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Prev", callback_data="teamopt_prev"),
         InlineKeyboardButton("1/3", callback_data="teamopt_noop"),
         InlineKeyboardButton("Next ▶️", callback_data="teamopt_next")],
        [InlineKeyboardButton("✅ Use This", callback_data="teamopt_select_0")],
        [InlineKeyboardButton("🔄 Regenerate All", callback_data=f"teams_{event_id}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"view_{event_id}")]
    ])
    
    context.user_data["team_option_index"] = 0
    
    await query.answer()
    await query.edit_message_text(
        f"🎲 *Team Generator*\n\n{format_team_option(1, options[0])}",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def team_option_nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Navigate between team options."""
    query = update.callback_query
    action = query.data.replace("teamopt_", "")
    
    options = context.user_data.get("team_options", [])
    current_index = context.user_data.get("team_option_index", 0)
    event_id = context.user_data.get("team_event_id")
    
    if not options or not event_id:
        await query.answer("Session expired. Please generate teams again.", show_alert=True)
        return
    
    if action == "prev":
        current_index = (current_index - 1) % 3
    elif action == "next":
        current_index = (current_index + 1) % 3
    elif action == "noop":
        await query.answer()
        return
    
    context.user_data["team_option_index"] = current_index
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Prev", callback_data="teamopt_prev"),
         InlineKeyboardButton(f"{current_index + 1}/3", callback_data="teamopt_noop"),
         InlineKeyboardButton("Next ▶️", callback_data="teamopt_next")],
        [InlineKeyboardButton("✅ Use This", callback_data=f"teamopt_select_{current_index}")],
        [InlineKeyboardButton("🔄 Regenerate All", callback_data=f"teams_{event_id}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"view_{event_id}")]
    ])
    
    await query.answer()
    await query.edit_message_text(
        f"🎲 *Team Generator*\n\n{format_team_option(current_index + 1, options[current_index])}",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def team_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select a team option and post to chat."""
    query = update.callback_query
    option_index = int(query.data.replace("teamopt_select_", ""))
    
    options = context.user_data.get("team_options", [])
    event_id = context.user_data.get("team_event_id")
    
    if not options or not event_id:
        await query.answer("Session expired. Please generate teams again.", show_alert=True)
        return
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    selected = options[option_index]
    team1, team2, team3 = selected
    
    # Format final teams message
    msg = f"⚽ *Teams for {event['name']}*\n\n"
    msg += f"🔴 *Team Red* ({len(team1)})\n"
    msg += "\n".join([f"  • {name}" for name in team1])
    msg += f"\n\n🔵 *Team Blue* ({len(team2)})\n"
    msg += "\n".join([f"  • {name}" for name in team2])
    msg += f"\n\n⚪ *Team White* ({len(team3)})\n"
    msg += "\n".join([f"  • {name}" for name in team3])
    msg += "\n\n_Good luck everyone!_ 🏆"
    
    await query.answer("Teams selected!")
    
    # Post to teams topic if configured
    chat_id = update.effective_chat.id
    settings = db.get_chat_settings(chat_id)
    teams_topic_id = settings.get("teams_topic_id")
    
    if teams_topic_id:
        # Post to dedicated teams topic
        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode="Markdown",
            message_thread_id=teams_topic_id
        )
        await query.edit_message_text("✅ Teams posted to Team Sheet topic!")
    else:
        # Just edit the current message
        await query.edit_message_text(msg, parse_mode="Markdown")
    
    # Clear session data
    context.user_data.pop("team_options", None)
    context.user_data.pop("team_event_id", None)
    context.user_data.pop("team_option_index", None)


async def old_remove_friend_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Deprecated - keeping for reference
    query = update.callback_query
    event_id = int(query.data.replace("removefriend_", ""))
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    # Get list of guests (friends) in this event
    participants = db.get_participants(event_id)
    guests = [p for p in participants if p["user_id"] < 0]
    
    if not guests:
        await query.answer("No friends to remove!", show_alert=True)
        return
    
    # Show buttons for each guest
    buttons = []
    for guest in guests:
        buttons.append([InlineKeyboardButton(
            f"❌ {guest['display_name']}", 
            callback_data=f"rmguest_{event_id}_{guest['user_id']}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"view_{event_id}")])
    
    await query.answer()
    await query.edit_message_text(
        "Select a friend to remove:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def remove_guest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Format: rmguest_{event_id}_{user_id}
    parts = query.data.split("_")
    event_id = int(parts[1])
    guest_id = int(parts[2])
    
    event = db.get_event(event_id)
    if not event:
        await query.answer("Event not found!", show_alert=True)
        return
    
    success = db.remove_participant(event_id, guest_id)
    
    if success:
        await query.answer("Friend removed!")
        participants = db.get_participants(event_id)
        await query.edit_message_text(
            format_event_message(event, participants),
            reply_markup=get_event_keyboard(event_id)
        )
    else:
        await query.answer("Failed to remove.", show_alert=True)


# ============ PAYMENT COMMANDS ============

async def mark_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /paid [event_id]")
        return

    try:
        event_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid event ID.")
        return

    event = db.get_event(event_id)
    user = update.effective_user
    success = db.set_payment_status(event_id, user.id, True)

    if success:
        if db.check_and_delete_fully_paid_event(event_id):
            await update.message.reply_text(f"✅ You're marked as paid!\n\n🎉 All payments complete - event archived!")
        else:
            await update.message.reply_text("✅ You're marked as paid!")
    else:
        await update.message.reply_text("You're not in this event or event doesn't exist.")


async def set_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /setpaid [event_id] @username or name")
        return

    try:
        event_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid event ID.")
        return

    event = db.get_event(event_id)
    if not event:
        await update.message.reply_text("Event not found.")
        return

    # Check for @mention
    if update.message.entities:
        for entity in update.message.entities:
            if entity.type == "text_mention":
                user_id = entity.user.id
                db.set_payment_status(event_id, user_id, True)
                if db.check_and_delete_fully_paid_event(event_id):
                    await update.message.reply_text(f"✅ Marked as paid!\n\n🎉 All payments complete - event archived!")
                else:
                    await update.message.reply_text(f"✅ Marked as paid!")
                return
            elif entity.type == "mention":
                username = update.message.text[entity.offset + 1:entity.offset + entity.length]
                participants = db.get_participants(event_id)
                for p in participants:
                    if p["username"] and p["username"].lower() == username.lower():
                        db.set_payment_status(event_id, p["user_id"], True)
                        if db.check_and_delete_fully_paid_event(event_id):
                            await update.message.reply_text(f"✅ @{username} marked as paid!\n\n🎉 All payments complete - event archived!")
                        else:
                            await update.message.reply_text(f"✅ @{username} marked as paid!")
                        return
                await update.message.reply_text(f"User @{username} not found in this event.")
                return

    # Try to match by name (for guests/friends)
    name_to_find = " ".join(context.args[1:])
    participants = db.get_participants(event_id)
    for p in participants:
        if p["display_name"] and p["display_name"].lower() == name_to_find.lower():
            db.set_payment_status(event_id, p["user_id"], True)
            if db.check_and_delete_fully_paid_event(event_id):
                await update.message.reply_text(f"✅ {p['display_name']} marked as paid!\n\n🎉 All payments complete - event archived!")
            else:
                await update.message.reply_text(f"✅ {p['display_name']} marked as paid!")
            return

    await update.message.reply_text("User not found. Use @username or exact name.")


async def view_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /payments <event_id>")
        return

    try:
        event_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid event ID.")
        return

    event = db.get_event(event_id)
    if not event:
        await update.message.reply_text("Event not found.")
        return

    summary = db.get_payment_summary(event_id)

    message = f"💰 *Payment Status for {event['name']}*\n\n"

    if summary["paid"]:
        message += "✅ *Paid:*\n"
        for p in summary["paid"]:
            name = p["display_name"] or p["username"] or "Unknown"
            message += f"  • {name}\n"
    else:
        message += "✅ *Paid:* _None_\n"

    message += "\n"

    if summary["unpaid"]:
        message += "❌ *Unpaid:*\n"
        for p in summary["unpaid"]:
            name = p["display_name"] or p["username"] or "Unknown"
            message += f"  • {name}\n"
    else:
        message += "❌ *Unpaid:* _None_\n"

    message += f"\n📊 {len(summary['paid'])}/{summary['total']} paid"

    await update.message.reply_text(message, parse_mode="Markdown")


# ============ REMINDER CONVERSATION ============

async def new_reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(day, callback_data=f"day_{i}")]
        for i, day in enumerate(DAYS_OF_WEEK)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🗓️ Set up court booking reminder\n\n"
        "This will remind you to ballot for a court 2 weeks in advance.\n\n"
        "Which day should I remind you?",
        reply_markup=reply_markup
    )
    return REMINDER_DAY


async def reminder_day_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    day_index = int(query.data.split("_")[1])
    context.user_data["reminder_day"] = day_index

    await query.edit_message_text(
        f"Selected: *{DAYS_OF_WEEK[day_index]}*\n\n"
        "What time should I send the reminder?\n(format: HH:MM, e.g., 09:00)",
        parse_mode="Markdown"
    )
    return REMINDER_TIME


async def reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = update.message.text
    try:
        time_obj = datetime.strptime(time_text, "%H:%M")
        hour = time_obj.hour
        minute = time_obj.minute
        chat_id = update.effective_chat.id
        
        # Static message for court booking
        message = "BOOKING_REMINDER"
        
        reminder_id = db.add_reminder(
            chat_id=chat_id,
            day_of_week=context.user_data["reminder_day"],
            hour=hour,
            minute=minute,
            message=message
        )

        # Schedule the reminder
        scheduler = context.bot_data.get("scheduler")
        if scheduler:
            schedule_reminder(scheduler, context.application, {
                "id": reminder_id,
                "chat_id": chat_id,
                "day_of_week": context.user_data["reminder_day"],
                "hour": hour,
                "minute": minute,
                "message": message
            })

        day_name = DAYS_OF_WEEK[context.user_data["reminder_day"]]
        time_str = f"{hour:02d}:{minute:02d}"

        await update.message.reply_text(
            f"✅ Reminder set!\n\n"
            f"📅 Every *{day_name}* at *{time_str}*\n"
            f"💬 Will remind to book court for 2 weeks ahead\n\n"
            f"Reminder ID: `{reminder_id}`",
            parse_mode="Markdown"
        )
        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Invalid time format. Please use HH:MM (e.g., 09:00)")
        return REMINDER_TIME


async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    reminders = db.get_reminders(chat_id)

    if not reminders:
        await update.message.reply_text("No active reminders for this chat.")
        return

    message = "⏰ *Active Reminders:*\n\n"
    for r in reminders:
        day_name = DAYS_OF_WEEK[r["day_of_week"]]
        time_str = f"{r['hour']:02d}:{r['minute']:02d}"
        message += f"*{r['id']}.* Every {day_name} at {time_str}\n   Court booking reminder (2 weeks ahead)\n\n"

    await update.message.reply_text(message, parse_mode="Markdown")


async def delete_reminder_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /deletereminder <reminder_id>")
        return

    try:
        reminder_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid reminder ID.")
        return

    db.delete_reminder(reminder_id)

    scheduler = context.bot_data.get("scheduler")
    if scheduler:
        try:
            scheduler.remove_job(f"reminder_{reminder_id}")
        except Exception:
            pass

    await update.message.reply_text(f"🗑️ Reminder {reminder_id} deleted.")


# ============ SCHEDULER ============

def schedule_reminder(scheduler: AsyncIOScheduler, app: Application, reminder: dict):
    async def send_reminder():
        # Calculate date 2 weeks from now
        booking_date = datetime.now() + timedelta(days=14)
        booking_date_str = booking_date.strftime("%A, %d %B")
        
        message = (
            f"⏰ *Time to book the court\\!*\n\n"
            f"🗓️ Ballot today for: *{booking_date_str}*\n\n"
            f"[Book at ActiveSG](https://activesg.gov.sg/facility-bookings/activities/CF6ecxA4HkJgUabDMGsWo/venues)"
        )
        
        # Get reminder topic if configured
        settings = db.get_chat_settings(reminder["chat_id"])
        reminder_topic_id = settings.get("reminder_topic_id")
        
        await app.bot.send_message(
            chat_id=reminder["chat_id"],
            text=message,
            parse_mode="MarkdownV2",
            message_thread_id=reminder_topic_id
        )

    scheduler.add_job(
        send_reminder,
        CronTrigger(day_of_week=reminder["day_of_week"], hour=reminder["hour"], minute=reminder["minute"]),
        id=f"reminder_{reminder['id']}",
        replace_existing=True
    )


def get_event_end_time(event: dict) -> datetime:
    """Calculate when an event ends based on date and time slot."""
    date_obj = datetime.strptime(event["date"], "%Y-%m-%d")
    time_str = event["time"]
    
    # Handle time slot format (e.g., "07:00-09:00")
    if "-" in time_str:
        end_time_str = time_str.split("-")[1]
    else:
        end_time_str = time_str
    
    end_time = datetime.strptime(end_time_str, "%H:%M")
    return date_obj.replace(hour=end_time.hour, minute=end_time.minute)


async def check_payment_reminders(app: Application):
    """Check for events that need payment reminders (1 hour after match ends)."""
    events = db.get_events_needing_payment_reminder()
    now = datetime.now()
    
    for event in events:
        end_time = get_event_end_time(event)
        reminder_time = end_time + timedelta(hours=1)
        
        if now >= reminder_time:
            # Get unpaid participants
            participants = db.get_participants(event["id"])
            unpaid = [p for p in participants if not p["paid"]]
            
            if unpaid and event.get("chat_id"):
                unpaid_names = "\n".join([f"• {p['display_name'] or p['username'] or 'Unknown'}" for p in unpaid])
                
                # Calculate per-person cost
                total_cost = event.get("total_cost", 0)
                num_participants = len(participants)
                cost_text = ""
                if total_cost > 0 and num_participants > 0:
                    per_person = total_cost / num_participants
                    cost_text = f"\n\n💵 *${total_cost:.2f} ÷ {num_participants} = ${per_person:.2f} per person*"
                
                booker_text = ""
                if event.get("booker_name"):
                    booker_info = event['booker_name']
                    if event.get("booker_number"):
                        booker_info += f"\n📱 PayNow: {event['booker_number']}"
                    booker_text = f"\n\n💳 Please pay {booker_info}"
                
                message = (
                    f"💰 *Payment Reminder*\n\n"
                    f"⚽ {event['name']}"
                    f"{cost_text}\n\n"
                    f"Still unpaid:\n{unpaid_names}"
                    f"{booker_text}"
                )
                
                try:
                    # Use payment topic if configured, otherwise use event's topic
                    settings = db.get_chat_settings(event["chat_id"])
                    payment_topic_id = settings.get("payment_topic_id") or event.get("message_thread_id")
                    
                    await app.bot.send_message(
                        chat_id=event["chat_id"],
                        text=message,
                        parse_mode="Markdown",
                        message_thread_id=payment_topic_id,
                        reply_markup=get_payment_keyboard(event["id"])
                    )
                except Exception as e:
                    logger.error(f"Failed to send payment reminder for event {event['id']}: {e}")
            
            # Mark reminder as sent
            db.mark_payment_reminder_sent(event["id"])


async def post_init(app: Application):
    """Called after the application is initialized, inside the async context."""
    scheduler = AsyncIOScheduler()
    
    # Schedule weekly reminders
    reminders = db.get_reminders()
    for reminder in reminders:
        schedule_reminder(scheduler, app, reminder)
    
    # Schedule payment reminder check every 5 minutes
    async def payment_check():
        await check_payment_reminders(app)
    
    scheduler.add_job(
        payment_check,
        'interval',
        minutes=5,
        id='payment_reminder_check',
        replace_existing=True
    )
    
    scheduler.start()
    app.bot_data["scheduler"] = scheduler
    logger.info("Scheduler started with %d reminders", len(reminders))


def main():
    db.init_db()
    
    # Try to restore from backup on startup
    if db.restore_from_gist():
        logger.info("Database restored from GitHub Gist backup")
    else:
        logger.info("No backup restored (new install or no backup configured)")

    app = Application.builder().token(TOKEN).post_init(post_init).build()

    # Filter for text messages (regular messages, channel posts, and forum topics)
    text_filter = filters.TEXT & ~filters.COMMAND
    
    # Event creation conversation (button-based)
    # per_chat=False allows conversation to continue across group->DM
    event_conv = ConversationHandler(
        entry_points=[
            CommandHandler("newevent", new_event_start, filters=filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP | filters.ChatType.PRIVATE),
            MessageHandler(filters.UpdateType.CHANNEL_POST & filters.Regex(r'^/newevent'), new_event_start)
        ],
        states={
            EVENT_DATE: [CallbackQueryHandler(event_date_callback, pattern=r"^(date_|cancel_)")],
            EVENT_TIME: [CallbackQueryHandler(event_time_callback, pattern=r"^(time_|cancel_)")],
            EVENT_LOC_SELECT: [CallbackQueryHandler(event_location_callback, pattern=r"^(loc_|cancel_)")],
            EVENT_MAX: [CallbackQueryHandler(event_max_callback, pattern=r"^(max_|cancel_)")],
            EVENT_BOOKER: [MessageHandler(text_filter, event_booker)],
            EVENT_BOOKER_NUMBER: [MessageHandler(text_filter, event_booker_number)],
            EVENT_COST: [MessageHandler(text_filter, event_cost)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel_callback, pattern=r"^cancel_event$")
        ],
        per_message=False,
        per_chat=False,
    )

    # Reminder creation conversation (simplified - just day and time)
    reminder_conv = ConversationHandler(
        entry_points=[CommandHandler("newreminder", new_reminder_start)],
        states={
            REMINDER_DAY: [CallbackQueryHandler(reminder_day_callback, pattern=r"^day_\d$")],
            REMINDER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(event_conv)
    app.add_handler(CommandHandler("events", list_events))
    app.add_handler(CommandHandler("event", view_event))

    # Inline button handlers for events
    app.add_handler(CallbackQueryHandler(paid_button_callback, pattern=r"^paid_\d+$"))
    app.add_handler(CallbackQueryHandler(toggle_paid_callback, pattern=r"^togglepaid_\d+_-?\d+$"))
    app.add_handler(CallbackQueryHandler(confirm_paid_callback, pattern=r"^confirmpaid_\d+$"))
    app.add_handler(CallbackQueryHandler(cancel_paid_callback, pattern=r"^cancelpaid_\d+$"))
    app.add_handler(CallbackQueryHandler(view_button_callback, pattern=r"^view_\d+$"))
    app.add_handler(CallbackQueryHandler(view_payment_callback, pattern=r"^viewpayment_\d+$"))
    app.add_handler(CallbackQueryHandler(remove_button_callback, pattern=r"^remove_\d+$"))
    app.add_handler(CallbackQueryHandler(remove_person_callback, pattern=r"^rm_\d+_-?\d+$"))
    
    # Edit event handlers
    app.add_handler(CallbackQueryHandler(edit_button_callback, pattern=r"^edit_\d+$"))
    app.add_handler(CallbackQueryHandler(edit_date_callback, pattern=r"^editdate_\d+$"))
    app.add_handler(CallbackQueryHandler(new_date_selected_callback, pattern=r"^newedate_"))
    app.add_handler(CallbackQueryHandler(edit_time_callback, pattern=r"^edittime_\d+$"))
    app.add_handler(CallbackQueryHandler(new_time_selected_callback, pattern=r"^newetime_"))
    app.add_handler(CallbackQueryHandler(edit_location_callback, pattern=r"^editloc_\d+$"))
    app.add_handler(CallbackQueryHandler(new_location_selected_callback, pattern=r"^neweloc_"))
    app.add_handler(CallbackQueryHandler(edit_topic_callback, pattern=r"^edittopic_\d+$"))
    app.add_handler(CallbackQueryHandler(set_topic_callback, pattern=r"^settopic_\d+$"))
    app.add_handler(CallbackQueryHandler(clear_topic_callback, pattern=r"^cleartopic_\d+$"))
    
    # Edit cost conversation
    edit_cost_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_cost_callback, pattern=r"^editcost_\d+$")],
        states={
            EDIT_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_cost_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
    app.add_handler(edit_cost_conv)
    
    # Team generation handlers
    app.add_handler(CallbackQueryHandler(teams_button_callback, pattern=r"^teams_\d+$"))
    app.add_handler(CallbackQueryHandler(team_option_nav_callback, pattern=r"^teamopt_(prev|next|noop)$"))
    app.add_handler(CallbackQueryHandler(team_select_callback, pattern=r"^teamopt_select_\d+$"))

    # Add person conversation
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_button_callback, pattern=r"^add_\d+$")],
        states={
            ADD_FRIEND_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
    app.add_handler(add_conv)

    app.add_handler(CommandHandler("paid", mark_paid))
    app.add_handler(CommandHandler("setpaid", set_paid))
    app.add_handler(CommandHandler("payments", view_payments))

    app.add_handler(reminder_conv)
    app.add_handler(CommandHandler("reminders", list_reminders))
    app.add_handler(CommandHandler("deletereminder", delete_reminder_cmd))
    
    # Topic setup handlers
    app.add_handler(CommandHandler("setuptopics", setup_topics))
    app.add_handler(CallbackQueryHandler(setup_topic_callback, pattern=r"^setuptopic_"))
    app.add_handler(CallbackQueryHandler(confirm_topic_callback, pattern=r"^confirmtopic$"))
    app.add_handler(CallbackQueryHandler(setup_topics_back_callback, pattern=r"^setuptopics_back$"))

    logger.info("Bot started!")
    
    # Create event loop and run
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
