from datetime import datetime
import logging
from typing import Optional, Union
import pytz

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from lunchable.models import TransactionObject

from utils import make_tag


logger = logging.getLogger("messaging")


def get_tx_buttons(
    transaction_id: int, plaid=True, skip=True, mark_reviewed=True, categorize=True
) -> InlineKeyboardMarkup:
    """Returns a list of buttons to be displayed for a transaction."""
    buttons = []
    if categorize:
        buttons.append(
            InlineKeyboardButton(
                "Categorize", callback_data=f"categorize_{transaction_id}"
            )
        )
    if plaid:
        buttons.append(
            InlineKeyboardButton(
                "Dump plaid details", callback_data=f"plaid_{transaction_id}"
            )
        )
    if skip:
        buttons.append(
            InlineKeyboardButton("Skip", callback_data=f"skip_{transaction_id}")
        )
    if mark_reviewed:
        buttons.append(
            InlineKeyboardButton(
                "Mark as reviewed", callback_data=f"review_{transaction_id}"
            )
        )
    # max two buttons per row
    buttons = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(buttons)


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
    category_group = transaction.category_group_name or "No Group"

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

    message = f"{make_tag(category_group, title=True)} {recurring}\n\n"
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

    # recurring transactions are not categorizable
    show_categorize = transaction.recurring_type is None

    if transaction.is_pending:
        # when a transaction is pending, we don't want to mark it as reviewed
        keyboard = get_tx_buttons(
            transaction.id, mark_reviewed=False, skip=False, categorize=show_categorize
        )
    else:
        keyboard = get_tx_buttons(transaction.id, categorize=show_categorize)

    if message_id:
        # edit existing message
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
        return message_id
    else:
        # send a new message
        logger.info(f"Sending message to chat_id {chat_id}: {message}")
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
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

    await query.edit_message_reply_markup(
        reply_markup=get_tx_buttons(transaction_id, plaid=False)
    )
