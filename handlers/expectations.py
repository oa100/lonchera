from typing import Dict, Optional


EXPECTING_TOKEN = "token"
current_expectation: Dict[int, Optional[Dict[str, str]]] = {}


def get_expectation(chat_id: int) -> Optional[Dict[str, str]]:
    return current_expectation.get(chat_id, None)


def set_expectation(chat_id: int, expectation: Optional[Dict[str, str]]):
    current_expectation[chat_id] = expectation
