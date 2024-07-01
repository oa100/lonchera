import logging
import sqlite3
from typing import Optional
from datetime import datetime

logger = logging.getLogger("db")

db_schema = """
CREATE TABLE IF NOT EXISTS transactions (
    message_id INTEGER PRIMARY KEY,
    tx_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL
)
"""


class Persistence:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.initialize_db()

    # Database initialization
    def initialize_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                message_id INTEGER PRIMARY KEY,
                tx_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()
        logger.info("Database initialized")

    # Function to check if a transaction ID has already been sent
    def already_sent(self, tx_id: int) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT 1 FROM transactions WHERE tx_id = ?", (tx_id,))
        result = c.fetchone()
        conn.close()
        return result is not None

    # Function to mark a transaction ID as sent with an associated message ID
    def mark_as_sent(self, tx_id: int, message_id: int) -> None:
        logger.info(f"Marking transaction {tx_id} as sent with message ID {message_id}")
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        timestamp = datetime.now().isoformat()
        c.execute(
            "INSERT INTO transactions (message_id, tx_id, timestamp) VALUES (?, ?, ?)",
            (message_id, tx_id, timestamp),
        )
        conn.commit()
        conn.close()

    # Function to get the transaction ID associated with a specific message ID
    def get_tx_associated_with(self, message_id: int) -> Optional[int]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT tx_id FROM transactions WHERE message_id = ?", (message_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

    def nuke(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DROP TABLE transactions")
        c.execute(db_schema)
        conn.commit()
        conn.close()
        logger.info("Database nuked")
