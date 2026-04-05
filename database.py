import sqlite3
import os
import json
import requests
from datetime import datetime
from typing import Optional

# Use local database
DB_PATH = "soccer_bot.db"

# GitHub Gist for backup (set these as environment variables)
GIST_ID = os.environ.get("GIST_ID", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def get_connection():
    return sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            location TEXT,
            max_players INTEGER DEFAULT 20,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            chat_id INTEGER,
            booker_name TEXT,
            booker_number TEXT,
            payment_reminder_sent INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0,
            message_thread_id INTEGER
        )
    """)

    # Add new columns if they don't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE events ADD COLUMN chat_id INTEGER")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE events ADD COLUMN booker_name TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE events ADD COLUMN booker_number TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE events ADD COLUMN payment_reminder_sent INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE events ADD COLUMN total_cost REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE events ADD COLUMN message_thread_id INTEGER")
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            display_name TEXT,
            paid INTEGER DEFAULT 0,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES events(id),
            UNIQUE(event_id, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,
            hour INTEGER NOT NULL,
            minute INTEGER NOT NULL,
            message TEXT NOT NULL,
            enabled INTEGER DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()


# Event functions
def create_event(name: str, date: str, time: str, location: str, max_players: int, created_by: int, chat_id: int = None, booker_name: str = None, booker_number: str = None, total_cost: float = 0, message_thread_id: int = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO events (name, date, time, location, max_players, created_by, chat_id, booker_name, booker_number, total_cost, message_thread_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, date, time, location, max_players, created_by, chat_id, booker_name, booker_number, total_cost, message_thread_id)
    )
    event_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return event_id


def get_event(event_id: int) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, date, time, location, max_players, created_by, chat_id, booker_name, booker_number, payment_reminder_sent, total_cost, message_thread_id FROM events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0], "name": row[1], "date": row[2], "time": row[3],
            "location": row[4], "max_players": row[5], "created_by": row[6],
            "chat_id": row[7], "booker_name": row[8], "booker_number": row[9], 
            "payment_reminder_sent": row[10], "total_cost": row[11] or 0,
            "message_thread_id": row[12]
        }
    return None


def get_upcoming_events() -> list:
    """Get events from today onwards."""
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT id, name, date, time, location, max_players, chat_id, booker_name, booker_number, total_cost, message_thread_id FROM events WHERE date >= ? ORDER BY date, time", (today,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "date": r[2], "time": r[3], "location": r[4], "max_players": r[5], "chat_id": r[6], "booker_name": r[7], "booker_number": r[8], "total_cost": r[9] or 0, "message_thread_id": r[10]}
        for r in rows
    ]


def update_event(event_id: int, **kwargs):
    """Update event fields. Pass field names as keyword arguments."""
    if not kwargs:
        return
    conn = get_connection()
    cursor = conn.cursor()
    
    set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [event_id]
    
    cursor.execute(f"UPDATE events SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def cleanup_old_events(days_old: int = 3) -> int:
    """Delete events older than X days. Returns number deleted."""
    conn = get_connection()
    cursor = conn.cursor()
    from datetime import timedelta
    cutoff_date = (datetime.now() - timedelta(days=days_old)).strftime("%Y-%m-%d")
    
    # Get IDs of old events
    cursor.execute("SELECT id FROM events WHERE date < ?", (cutoff_date,))
    old_event_ids = [row[0] for row in cursor.fetchall()]
    
    if old_event_ids:
        # Delete participants first
        cursor.execute(f"DELETE FROM participants WHERE event_id IN ({','.join('?' * len(old_event_ids))})", old_event_ids)
        # Delete events
        cursor.execute(f"DELETE FROM events WHERE id IN ({','.join('?' * len(old_event_ids))})", old_event_ids)
    
    conn.commit()
    conn.close()
    return len(old_event_ids)


def get_events_needing_payment_reminder() -> list:
    """Get events that ended more than 1 hour ago and haven't had payment reminder sent."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, date, time, location, max_players, created_by, chat_id, booker_name, booker_number, total_cost, message_thread_id 
        FROM events 
        WHERE payment_reminder_sent = 0 AND chat_id IS NOT NULL
    """)
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "date": r[2], "time": r[3], "location": r[4], 
         "max_players": r[5], "created_by": r[6], "chat_id": r[7], "booker_name": r[8], "booker_number": r[9], "total_cost": r[10] or 0, "message_thread_id": r[11]}
        for r in rows
    ]


def mark_payment_reminder_sent(event_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE events SET payment_reminder_sent = 1 WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()


def delete_event(event_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM participants WHERE event_id = ?", (event_id,))
    cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()


def check_and_delete_fully_paid_event(event_id: int) -> bool:
    """Delete event if all participants have paid. Returns True if deleted."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM participants WHERE event_id = ? AND paid = 0", (event_id,))
    unpaid_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM participants WHERE event_id = ?", (event_id,))
    total_count = cursor.fetchone()[0]
    conn.close()
    
    if total_count > 0 and unpaid_count == 0:
        delete_event(event_id)
        return True
    return False


# Participant functions
def add_participant(event_id: int, user_id: int, username: str, display_name: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO participants (event_id, user_id, username, display_name) VALUES (?, ?, ?, ?)",
            (event_id, user_id, username, display_name)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def add_guest(event_id: int, guest_name: str, added_by: int) -> bool:
    """Add a guest (friend without Telegram). Uses negative IDs to avoid conflicts."""
    conn = get_connection()
    cursor = conn.cursor()
    # Generate a unique negative ID for guests
    cursor.execute("SELECT MIN(user_id) FROM participants")
    min_id = cursor.fetchone()[0]
    guest_id = -1 if min_id is None or min_id >= 0 else min_id - 1
    
    try:
        cursor.execute(
            "INSERT INTO participants (event_id, user_id, username, display_name) VALUES (?, ?, ?, ?)",
            (event_id, guest_id, f"guest_{added_by}", guest_name)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def remove_participant(event_id: int, user_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM participants WHERE event_id = ? AND user_id = ?", (event_id, user_id))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def remove_guest_by_name(event_id: int, guest_name: str) -> bool:
    """Remove a guest by their display name."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM participants WHERE event_id = ? AND display_name = ? AND user_id < 0",
        (event_id, guest_name)
    )
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_participants(event_id: int) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, username, display_name, paid FROM participants WHERE event_id = ? ORDER BY joined_at",
        (event_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"user_id": r[0], "username": r[1], "display_name": r[2], "paid": bool(r[3])} for r in rows]


def set_payment_status(event_id: int, user_id: int, paid: bool) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE participants SET paid = ? WHERE event_id = ? AND user_id = ?",
        (1 if paid else 0, event_id, user_id)
    )
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def get_payment_summary(event_id: int) -> dict:
    participants = get_participants(event_id)
    paid = [p for p in participants if p["paid"]]
    unpaid = [p for p in participants if not p["paid"]]
    return {"paid": paid, "unpaid": unpaid, "total": len(participants)}


# Reminder functions
def add_reminder(chat_id: int, day_of_week: int, hour: int, minute: int, message: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reminders (chat_id, day_of_week, hour, minute, message) VALUES (?, ?, ?, ?, ?)",
        (chat_id, day_of_week, hour, minute, message)
    )
    reminder_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return reminder_id


def get_reminders(chat_id: int = None) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    if chat_id:
        cursor.execute("SELECT * FROM reminders WHERE chat_id = ? AND enabled = 1", (chat_id,))
    else:
        cursor.execute("SELECT * FROM reminders WHERE enabled = 1")
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "chat_id": r[1], "day_of_week": r[2], "hour": r[3], "minute": r[4], "message": r[5]}
        for r in rows
    ]


def delete_reminder(reminder_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


# ============ BACKUP/RESTORE TO GITHUB GIST ============

def export_to_json() -> dict:
    """Export all data to a JSON-serializable dict."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Export events
    cursor.execute("SELECT * FROM events")
    events = []
    for row in cursor.fetchall():
        events.append({
            "id": row[0], "name": row[1], "date": row[2], "time": row[3],
            "location": row[4], "max_players": row[5], "created_by": row[6],
            "created_at": str(row[7]) if row[7] else None, "chat_id": row[8],
            "booker_name": row[9], "booker_number": row[10], "payment_reminder_sent": row[11],
            "total_cost": row[12] if len(row) > 12 else 0,
            "message_thread_id": row[13] if len(row) > 13 else None
        })
    
    # Export participants
    cursor.execute("SELECT * FROM participants")
    participants = []
    for row in cursor.fetchall():
        participants.append({
            "id": row[0], "event_id": row[1], "user_id": row[2],
            "username": row[3], "display_name": row[4], "paid": row[5],
            "joined_at": str(row[6]) if row[6] else None
        })
    
    # Export reminders
    cursor.execute("SELECT * FROM reminders")
    reminders = []
    for row in cursor.fetchall():
        reminders.append({
            "id": row[0], "chat_id": row[1], "day_of_week": row[2],
            "hour": row[3], "minute": row[4], "message": row[5], "enabled": row[6]
        })
    
    conn.close()
    
    return {
        "exported_at": datetime.now().isoformat(),
        "events": events,
        "participants": participants,
        "reminders": reminders
    }


def import_from_json(data: dict):
    """Import data from JSON dict, replacing existing data."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Clear existing data
    cursor.execute("DELETE FROM participants")
    cursor.execute("DELETE FROM events")
    cursor.execute("DELETE FROM reminders")
    
    # Import events
    for e in data.get("events", []):
        cursor.execute("""
            INSERT INTO events (id, name, date, time, location, max_players, created_by, chat_id, booker_name, booker_number, payment_reminder_sent, total_cost, message_thread_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (e["id"], e["name"], e["date"], e["time"], e["location"], e["max_players"], 
              e["created_by"], e.get("chat_id"), e.get("booker_name"), e.get("booker_number"), e.get("payment_reminder_sent", 0), e.get("total_cost", 0), e.get("message_thread_id")))
    
    # Import participants
    for p in data.get("participants", []):
        cursor.execute("""
            INSERT INTO participants (id, event_id, user_id, username, display_name, paid)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (p["id"], p["event_id"], p["user_id"], p["username"], p["display_name"], p["paid"]))
    
    # Import reminders
    for r in data.get("reminders", []):
        cursor.execute("""
            INSERT INTO reminders (id, chat_id, day_of_week, hour, minute, message, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (r["id"], r["chat_id"], r["day_of_week"], r["hour"], r["minute"], r["message"], r.get("enabled", 1)))
    
    conn.commit()
    conn.close()


def backup_to_gist():
    """Backup database to GitHub Gist."""
    if not GIST_ID or not GITHUB_TOKEN:
        return False
    
    try:
        data = export_to_json()
        response = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            },
            json={
                "files": {
                    "soccer_bot_backup.json": {
                        "content": json.dumps(data, indent=2)
                    }
                }
            }
        )
        return response.status_code == 200
    except Exception:
        return False


def restore_from_gist():
    """Restore database from GitHub Gist."""
    if not GIST_ID or not GITHUB_TOKEN:
        return False
    
    try:
        response = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        if response.status_code == 200:
            gist_data = response.json()
            content = gist_data["files"]["soccer_bot_backup.json"]["content"]
            data = json.loads(content)
            import_from_json(data)
            return True
    except Exception:
        pass
    return False
