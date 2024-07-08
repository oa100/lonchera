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
        self.append(other)
        return self

    def build(self, columns: int = 2) -> InlineKeyboardMarkup:
        buttons = [
            InlineKeyboardButton(text, callback_data=data) for (text, data) in self
        ]
        buttons = [buttons[i : i + columns] for i in range(0, len(buttons), columns)]
        return InlineKeyboardMarkup(buttons)


def get_emoji_for_account_type(acct_type: str) -> str:
    if acct_type == "credit":
        return "💳"
    if acct_type == "depository":
        return "🏦"
    if acct_type == "investment":
        return "📈"
    if acct_type == "cash":
        return "💵"
    if acct_type == "loan":
        return "💸"
    if acct_type == "real estate":
        return "🏠"
    if acct_type == "vehicle":
        return "🚗"
    if acct_type == "cryptocurrency":
        return "₿"
    if acct_type == "employee compensation":
        return "👨‍💼"
    if acct_type == "other liability":
        return "📉"
    if acct_type == "other asset":
        return "📊"
    return "❓"


def get_crypto_symbol(crypto_name: str) -> str:
    crypto_symbols = {
        "bitcoin": "₿",
        "ethereum": "Ξ",
        "litecoin": "Ł",
        "ripple": "X",
        "bitcoin cash": "₿",
        "dogecoin": "Ð",
        "monero": "ɱ",
        "dash": "D",
        "nem": "ξ",
        "neo": "文",
        "stellar": "*",
        "zcash": "ⓩ",
        "cardano": "₳",
        "eos": "ε",
        "iota": "ι",
    }

    return crypto_symbols.get(crypto_name.lower(), crypto_name)
