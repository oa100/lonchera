from datetime import datetime
import io
import os
import requests
from typing import List
import pytz

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
from telegram.constants import ParseMode, ReactionEmoji
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from lunchable import LunchMoney
from lunchable.models import TransactionObject, TransactionUpdateObject

already_sent_transactions: List[int] = []

async def send_transaction_message(context: ContextTypes.DEFAULT_TYPE, transaction: TransactionObject, chat_id: str) -> None:
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
        formatted_date_time = "N/A"

    # Get category and category group
    category = transaction.category_name or "Uncategorized"
    category_group = transaction.category_group_name or "No Group"

    # Get account display name
    account_name = transaction.plaid_account_display_name or "N/A"

    message = f"*{category_group}*\n\n"
    message += f"*Payee:* {transaction.payee}\n"
    message += f"*Amount:* {formatted_amount}\n"
    message += f"*Date/Time:* {formatted_date_time}\n"
    message += f"*Category:* {category} \n"
    message += f"*Account:* {account_name}\n"


    keyboard = [
        [InlineKeyboardButton("Mark as Reviewed", callback_data=f"review_{transaction.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Check if category image is available
    category_image_url = transaction.plaid_metadata.get('personal_finance_category_icon_url')
    if category_image_url and False: # this is disabled for now
        try:
            # Download the image
            response = requests.get(category_image_url)
            response.raise_for_status()
            image_data = io.BytesIO(response.content)
            image_data.name = "category_image.png"

            photo = InputMediaPhoto(
                media=image_data,
                caption=message,
                parse_mode=ParseMode.MARKDOWN
            )

            # Send document with thumbnail
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                # caption=message,
                # parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        except Exception as e:
            print("Failed to send doc: ", e)
            
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=category_image_url,
                caption=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
    else:
        # Send message without image
        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

def setup_handlers(config):
    application = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()

    # Store necessary data in bot_data
    # application.bot_data["LUNCH_MONEY_TOKEN"] = config["LUNCH_MONEY_TOKEN"]
    # application.bot_data["TELEGRAM_CHAT_ID"] = config["TELEGRAM_CHAT_ID"]

    lunch = LunchMoney(access_token=config["LUNCH_MONEY_TOKEN"])

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Bot started. Use /check_transactions to fetch unreviewed transactions.")

    async def check_transactions_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        transactions = check_transactions_auto(context)
        
        if not transactions:
            await update.message.reply_text("No unreviewed transactions found.")
            return

    async def check_transactions_auto(context: ContextTypes.DEFAULT_TYPE) -> None:
        transactions = lunch.get_transactions(status='uncleared', pending=False)
        
        for transaction in transactions:
            if transaction.id in already_sent_transactions:
                print('Ignoring already sent transaction: ', transaction.id)
                continue
            already_sent_transactions.append(transaction.id)
            await send_transaction_message(context, transaction, config["TELEGRAM_CHAT_ID"])

        return transactions

    async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        transaction_id = int(query.data.split("_")[1])
        
        try:
            lunch.update_transaction(transaction_id, TransactionUpdateObject(status='cleared'))

            # Remove the inline keyboard (button)
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e:
            await query.edit_message_text(text=f"Error updating transaction: {str(e)}")

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check_transactions", check_transactions_manual))
    application.add_handler(CallbackQueryHandler(button_callback))

    job_queue = application.job_queue
    job_queue.run_repeating(check_transactions_auto, interval=1800, first=1)

    return application


def load_config():
    load_dotenv()
    
    return {
        "LUNCH_MONEY_TOKEN": os.getenv("LUNCH_MONEY_TOKEN"),
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID")
    }


def main():
    config = load_config()
    application = setup_handlers(config)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()