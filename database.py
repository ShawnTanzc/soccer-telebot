import sqlite3
from datetime import datetime
from typing import Optional

DB_PATH = "soccer_bot.db"


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
            payment_reminder_sent INTEGER DEFAULT 0
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
def create_event(name: str, date: str, time: str, location: str, max_players: int, created_by: int, chat_id: int = None, booker_name: str = None, booker_number: str = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO events (name, date, time, location, max_players, created_by, chat_id, booker_name, booker_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, date, time, location, max_players, created_by, chat_id, booker_name, booker_number)
    )
    event_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return event_id


def get_event(event_id: int) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, date, time, location, max_players, created_by, chat_id, booker_name, booker_number, payment_reminder_sent FROM events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0], "name": row[1], "date": row[2], "time": row[3],
            "location": row[4], "max_players": row[5], "created_by": row[6],
            "chat_id": row[7], "booker_name": row[8], "booker_number": row[9], "payment_reminder_sent": row[10]
        }
    return None


def get_upcoming_events() -> list:
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT id, name, date, time, location, max_players, chat_id, booker_name, booker_number FROM events WHERE date >= ? ORDER BY date, time", (today,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "date": r[2], "time": r[3], "location": r[4], "max_players": r[5], "chat_id": r[6], "booker_name": r[7], "booker_number": r[8]}
        for r in rows
    ]


def get_events_needing_payment_reminder() -> list:
    """Get events that ended more than 1 hour ago and haven't had payment reminder sent."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, date, time, location, max_players, created_by, chat_id, booker_name, booker_number 
        FROM events 
        WHERE payment_reminder_sent = 0 AND chat_id IS NOT NULL
    """)
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "date": r[2], "time": r[3], "location": r[4], 
         "max_players": r[5], "created_by": r[6], "chat_id": r[7], "booker_name": r[8], "booker_number": r[9]}
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
