from typing import List, Optional
from lunchable.models import TransactionObject


def make_tag(t: str):
    t = t.title().replace(" ", "").replace(".", "")
    return f"#{t}"


def find_related_tx(
    tx: TransactionObject, txs: List[TransactionObject]
) -> Optional[TransactionObject]:
    for t in txs:
        if t.amount == -tx.amount and (t.date == tx.date or t.payee == t.payee):
            return t
    return None
