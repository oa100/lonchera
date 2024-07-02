import logging
import os
import sqlite3
from typing import List, Optional, Union
from datetime import datetime

logger = logging.getLogger("db")

db_schema = """
CREATE TABLE IF NOT EXISTS transactions (
    message_id INTEGER NOT NULL,
    tx_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS tokens (
    chat_id INTEGER PRIMARY KEY,
    token TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


# TODO keep just one connection around
class Persistence:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.initialize_db()

    # Database initialization
    def initialize_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        for create_stmt in db_schema.split(";"):
            c.execute(create_stmt)
        conn.commit()
        conn.close()
        logger.info("Database initialized")

    def save_token(self, chat_id: int, token: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        timestamp = datetime.now().isoformat()
        c.execute(
            "INSERT INTO tokens (chat_id, token, created_at) VALUES (?, ?, ?)",
            (chat_id, token, timestamp),
        )
        conn.commit()
        conn.close()

    def get_token(self, chat_id) -> Union[str, None]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT token FROM tokens WHERE chat_id = ?", (chat_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

    def get_all_registered_chats(self) -> List[int]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT chat_id FROM tokens")
        result = c.fetchall()
        conn.close()
        return result

    # Function to check if a transaction ID has already been sent
    def already_sent(self, tx_id: int) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT 1 FROM transactions WHERE tx_id = ?", (tx_id,))
        result = c.fetchone()
        conn.close()
        return result is not None

    # Function to mark a transaction ID as sent with an associated message ID
    def mark_as_sent(self, tx_id: int, chat_id: int, message_id: int) -> None:
        logger.info(f"Marking transaction {tx_id} as sent with message ID {message_id}")
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        timestamp = datetime.now().isoformat()
        c.execute(
            "INSERT INTO transactions (message_id, tx_id, chat_id, created_at) VALUES (?, ?, ?, ?)",
            (message_id, tx_id, chat_id, timestamp),
        )
        conn.commit()
        conn.close()

    # Function to get the transaction ID associated with a specific message ID
    def get_tx_associated_with(self, message_id: int, chat_id: int) -> Optional[int]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT tx_id FROM transactions WHERE message_id = ? AND chat_id = ?",
            (
                message_id,
                chat_id,
            ),
        )
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

    def get_message_id_associated_with(self, tx_id: int, chat_id: int) -> Optional[int]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT message_id FROM transactions WHERE tx_id = ? AND chat_id = ?",
            (
                tx_id,
                chat_id,
            ),
        )
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

    def nuke(self, chat_id: int):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM transactions WHERE chat_id = ?", (chat_id,))
        conn.commit()
        conn.close()
        logger.info(f"Transactions deleted for chat {chat_id}")

    def mark_as_reviewed(self, message_id: int, chat_id: int):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        timestamp = datetime.now().isoformat()
        c.execute(
            "UPDATE transactions SET reviewed_at = ? WHERE message_id = ? AND chat_id = ?",
            (timestamp, message_id, chat_id),
        )
        conn.commit()
        conn.close()


db = None


def get_db() -> Persistence:
    global db
    if db is None:
        db = Persistence(os.getenv("DB_PATH", "lunchable.db"))
    return db
