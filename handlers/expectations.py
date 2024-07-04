from typing import Optional


EXPECTING_TOKEN = "token"
current_expectation = {}


def get_expectation(chat_id: int) -> Optional[str]:
    return current_expectation.get(chat_id, None)


def set_expectation(chat_id: int, expectation: str):
    current_expectation[chat_id] = expectation
