from datetime import datetime
import logging
import pytz

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from lunchable.models import TransactionObject

logger = logging.getLogger('messaging')


def get_buttons(transaction_id: int, plaid=True, skip=True, mark_reviewed=True, categorize=True):
    buttons = []
    if categorize:
        buttons.append(InlineKeyboardButton("Categorize", callback_data=f"categorize_{transaction_id}"))
    if plaid:
        buttons.append(InlineKeyboardButton("Dump plaid details", callback_data=f"plaid_{transaction_id}"))
    if skip:
        buttons.append(InlineKeyboardButton("Skip", callback_data=f"skip_{transaction_id}"))
    if mark_reviewed:
        buttons.append(InlineKeyboardButton("Mark as Reviewed", callback_data=f"review_{transaction_id}"))
    # max two buttons per row
    buttons = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return buttons

async def send_transaction_message(context: ContextTypes.DEFAULT_TYPE, transaction: TransactionObject, chat_id, message_id=None) -> None:
    # Format the amount with monospaced font
    formatted_amount = f"`${transaction.amount:.2f}`"

    # Get the datetime from plaid_metadata
    authorized_datetime = transaction.plaid_metadata.get('authorized_datetime')
    if authorized_datetime:
        date_time = datetime.fromisoformat(authorized_datetime.replace('Z', '+00:00'))
        pst_tz = pytz.timezone('US/Pacific')
        pst_date_time = date_time.astimezone(pst_tz)
        formatted_date_time = pst_date_time.strftime("%Y-%m-%d %I:%M:%S %p PST")
    else:
        formatted_date_time = transaction.plaid_metadata.get('date')

    # Get category and category group
    category = transaction.category_name or "Uncategorized"
    category_group = transaction.category_group_name or "No Group"

    # Get account display name
    account_name = transaction.plaid_account_display_name or "N/A"

    # split the category group into two: the first emoji and the rest of the string
    emoji, rest = category_group.split(" ", 1)

    message = f"{emoji} #*{rest.replace(" ", "_")}*\n\n"
    message += f"*Payee:* {transaction.payee}\n"
    message += f"*Amount:* {formatted_amount}\n"
    message += f"*Date/Time:* {formatted_date_time}\n"
    message += f"*Category:* #{category.title().replace(" ", "")} \n"
    message += f"*Account:* #{account_name}\n"


    keyboard = get_buttons(transaction.id)
    reply_markup = InlineKeyboardMarkup(keyboard)

    if message_id:
        # edit existing message
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    else:
        # send a new message
        logger.info(f"Sending message to chat_id {chat_id}: {message}")
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        context.bot_data[msg.id] = transaction.id
        logger.info(f"Current bot data: {context.bot_data}")


async def send_plaid_details(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, chat_id: int, transaction_id: str, plaid_details: str):
    await context.bot.send_message(
        chat_id=chat_id,
        text=plaid_details,
        parse_mode=ParseMode.MARKDOWN,
        reply_to_message_id=query.message.message_id,
    )

    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(get_buttons(transaction_id, plaid=False)))