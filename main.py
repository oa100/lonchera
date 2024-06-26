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
    message += f"*Category:* #{category} \n"
    message += f"*Account:* #{account_name}\n"


    keyboard = get_buttons(transaction.id)
    reply_markup = InlineKeyboardMarkup(keyboard)

    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

def setup_handlers(config):
    application = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()

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
            await send_transaction_message(context, transaction, '378659027')

        return transactions

    async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        print("query.data", query.data)

        chat_id = query.message.chat.id
        await query.answer()

        if query.data.startswith("skip"):
            await query.edit_message_reply_markup(reply_markup=None)
            return
        
        transaction_id = int(query.data.split("_")[1])
        
        if query.data.startswith("cancelCategorization"):
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(get_buttons(transaction_id)))
            return

        if query.data.startswith("categorize"):
            transaction = lunch.get_transaction(transaction_id)
            categories = lunch.get_categories()
            category_buttons = []
            for category in categories:
                if category.group_id is None:
                    category_buttons.append(InlineKeyboardButton(category.name, callback_data=f"subcategorize_{transaction_id}_{category.id}"))
            category_buttons = [category_buttons[i:i + 3] for i in range(0, len(category_buttons), 3)]
            category_buttons.append([InlineKeyboardButton("Cancel", callback_data=f"cancelCategorization_{transaction_id}")])
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(category_buttons))
            return
        
        if query.data.startswith("subcategorize"):
            transaction_id, category_id = query.data.split("_")[1:]
            subcategories = lunch.get_categories()
            subcategory_buttons = []
            for subcategory in subcategories:
                if str(subcategory.group_id) == str(category_id):
                    subcategory_buttons.append(InlineKeyboardButton(subcategory.name, callback_data=f"applyCategory_{transaction_id}_{subcategory.id}"))
            subcategory_buttons = [subcategory_buttons[i:i + 3] for i in range(0, len(subcategory_buttons), 3)]
            subcategory_buttons.append([InlineKeyboardButton("Cancel", callback_data=f"cancelCategorization_{transaction_id}")])
            
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(subcategory_buttons))
            return
        
        if query.data.startswith("applyCategory"):
            transaction_id, category_id = query.data.split("_")[1:]
            lunch.update_transaction(transaction_id, TransactionUpdateObject(category_id=category_id))
            updated_transaction = lunch.get_transaction(transaction_id)
            await send_transaction_message(context, updated_transaction, chat_id, query.message.message_id)
            return
        
        if query.data.startswith("plaid"):
            transaction = lunch.get_transaction(transaction_id)
            plaid_metadata = transaction.plaid_metadata
            plaid_details = f"*Plaid Metadata*\n\n"
            for key, value in plaid_metadata.items():
                if value is not None:
                    plaid_details += f"*{key}:* `{value}`\n"
            await context.bot.send_message(
                chat_id=chat_id,
                text=plaid_details,
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=query.message.message_id,
            )

            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(get_buttons(transaction_id, plaid=False)))
            return
        
        if query.data.startswith("review"):
            try:
                lunch.update_transaction(transaction_id, TransactionUpdateObject(status='cleared'))

                # Remove the inline keyboard (button)
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception as e:
                await query.edit_message_text(text=f"Error updating transaction: {str(e)}")
            return
        
        await context.bot.send_message(chat_id=chat_id, text="Unknown command")

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
    }


def main():
    config = load_config()
    application = setup_handlers(config)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()