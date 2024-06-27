from datetime import datetime
import logging
import pytz

from telegram import InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from lunchable.models import TransactionObject

from buttons import get_buttons

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger('messaging')

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

