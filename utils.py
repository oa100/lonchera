from typing import List, Optional
from lunchable.models import TransactionObject
import emoji


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
