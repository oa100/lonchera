from typing import List, Optional
from lunchable.models import TransactionObject
import emoji
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update


def is_emoji(char):
    return char in emoji.EMOJI_DATA


def make_tag(t: str, title=False):
    tag = "".join([char for char in t if char not in emoji.EMOJI_DATA])
    tag = tag.title().replace(" ", "").replace(".", "").strip()

    emojis = "".join([char for char in t if char in emoji.EMOJI_DATA])
    if title:
        return f"{emojis} *#{tag}*"
    else:
        return f"{emojis} #{tag}"


def find_related_tx(
    tx: TransactionObject, txs: List[TransactionObject]
) -> Optional[TransactionObject]:
    for t in txs:
        if t.amount == -tx.amount and (t.date == tx.date or t.payee == t.payee):
            return t
    return None


def get_chat_id(update: Update) -> int:
    if update.message:
        return update.message.chat_id

    if update.callback_query:
        return update.callback_query.message.chat.id

    raise ValueError(f"Could not find chat_id in {update}")


class Keyboard(list):
    def __iadd__(self, other):
        print(other)
        self.append(other)
        return self

    def build(self, max_per_row: int = 2) -> InlineKeyboardMarkup:
        buttons = [
            InlineKeyboardButton(text, callback_data=data) for (text, data) in self
        ]
        buttons = [
            buttons[i : i + max_per_row] for i in range(0, len(buttons), max_per_row)
        ]
        return InlineKeyboardMarkup(buttons)
