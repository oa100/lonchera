from datetime import datetime
import logging
from typing import Optional, Union
import pytz

from telegram import CallbackQuery, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from lunchable.models import TransactionObject

from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from utils import Keyboard, make_tag


logger = logging.getLogger("messaging")


def get_tx_buttons(
    transaction: Union[TransactionObject, int],
    collapsed=True,
) -> InlineKeyboardMarkup:
    """Returns a list of buttons to be displayed for a transaction."""
    # if transaction is an int, it's a transaction_id
    if isinstance(transaction, int):
        transaction_id = transaction
        # assume the transaction is persisted if a transaction_id is provided
        tx_metadata = get_db().get_tx_metadata(transaction_id)
        if tx_metadata is None:
            raise ValueError(f"Transaction {transaction_id} not in the database")
        recurring_type, is_pending, is_reviewed = tx_metadata
    else:
        transaction_id = transaction.id
        recurring_type = transaction.recurring_type
        is_pending = transaction.is_pending
        is_reviewed = transaction.status == "cleared"

    kbd = Keyboard()
    if collapsed:
        kbd += ("☷", f"moreOptions_{transaction_id}")

    # recurring transactions are not categorizable
    categorize = recurring_type is None
    if categorize and not collapsed:
        kbd += ("Categorize", f"categorize_{transaction_id}")

    if not collapsed:
        kbd += ("Rename payee", f"renamePayee_{transaction_id}")
        kbd += ("Edit notes", f"editNotes_{transaction_id}")
        kbd += ("Set tags", f"setTags_{transaction_id}")
        kbd += ("Dump plaid details", f"plaid_{transaction_id}")

        skip = not is_pending
        if skip and not is_reviewed:
            kbd += ("Skip", f"skip_{transaction_id}")

        if is_reviewed:
            kbd += ("Mark as unreviewed", f"unreview_{transaction_id}")

    if not is_reviewed:
        kbd += ("Mark as reviewed", f"review_{transaction_id}")

    if not is_pending and not collapsed and is_reviewed:
        kbd += ("⬒ Collapse", f"collapse_{transaction_id}")

    return kbd.build()


async def send_transaction_message(
    context: ContextTypes.DEFAULT_TYPE,
    transaction: TransactionObject,
    chat_id: Union[str, int],
    message_id: Optional[int] = None,
    reply_to_message_id: Optional[int] = None,
) -> int:
    """Sends a message to the chat_id with the details of a transaction.
    If message_id is provided, edits the existing"""
    # Get the datetime from plaid_metadata
    authorized_datetime = transaction.plaid_metadata.get("authorized_datetime")
    if authorized_datetime:
        date_time = datetime.fromisoformat(authorized_datetime.replace("Z", "-02:00"))
        pst_tz = pytz.timezone("US/Pacific")
        pst_date_time = date_time.astimezone(pst_tz)
        formatted_date_time = pst_date_time.strftime("%a, %b %d at %I:%M %p PST")
    else:
        formatted_date_time = transaction.plaid_metadata.get("date")

    # Get category and category group
    category = transaction.category_name or "Uncategorized"
    category_group = transaction.category_group_name
    if category is None:
        category_group = "*No Group*"
    else:
        category_group = make_tag(category_group, title=True)

    # Get account display name
    account_name = transaction.plaid_account_display_name or "N/A"

    recurring = ""
    if transaction.recurring_type:
        recurring = "(recurring 🔄)"

    explicit_sign = ""
    if transaction.amount < 0:
        # lunch money shows credits as negative
        # here I just want to denote that this was a credit by
        # explicitly showing a + sign before the amount
        explicit_sign = "➕"

    is_reviewed = transaction.status == "cleared"
    if is_reviewed:
        reviewed_watermark = "\u200B"
    else:
        reviewed_watermark = "\u200C"

    message = f"{category_group} {reviewed_watermark} {recurring}\n\n"
    message += f"*Payee*: {transaction.payee}\n"
    message += f"*Amount*: `{explicit_sign}{abs(transaction.amount):.2f}``{transaction.currency}`\n"
    message += f"*Date/Time*: {formatted_date_time}\n"
    message += f"*Category*: {make_tag(category)} \n"
    message += f"*Account*: {make_tag(account_name)}\n"
    if transaction.notes:
        message += f"*Notes*: {transaction.notes}\n"
    if transaction.tags:
        tags = [f"#{tag.name}" for tag in transaction.tags]
        message += f"*Tags*: {', '.join(tags)}\n"
    if transaction.is_pending:
        message += "\n_This is a pending transaction_\n"

    logger.info(f"Sending message to chat_id {chat_id}: {message}")
    if message_id:
        # edit existing message
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_tx_buttons(transaction),
            )
        except Exception as e:
            if "Message is not modified" in str(e):
                logger.info(f"Message {message_id} is not modified, skipping edit")
            else:
                raise e
        return message_id
    else:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_tx_buttons(transaction),
            reply_to_message_id=reply_to_message_id,
        )
        return msg.id


async def send_plaid_details(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    transaction_id: int,
    plaid_details: str,
):
    """Sends the plaid details of a transaction to the chat_id."""
    await context.bot.send_message(
        chat_id=chat_id,
        text=plaid_details,
        parse_mode=ParseMode.MARKDOWN,
        reply_to_message_id=query.message.message_id,
    )

    lunch = get_lunch_client_for_chat_id(chat_id)
    transaction = lunch.get_transaction(transaction_id)

    await query.edit_message_reply_markup(reply_markup=get_tx_buttons(transaction))
