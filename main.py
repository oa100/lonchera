from datetime import datetime
import logging
import os
from typing import List
import pytz

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode, ReactionEmoji
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from lunchable import LunchMoney
from lunchable.models import TransactionObject, TransactionUpdateObject

from buttons import apply_category, show_categories, get_buttons, show_subcategories
from messaging import send_transaction_message

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger('lonchera')

httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)

already_sent_transactions: List[int] = []

def setup_handlers(config):
    application = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()

    lunch = LunchMoney(access_token=config["LUNCH_MONEY_TOKEN"])

    async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Bot started. Use /check_transactions to fetch unreviewed transactions.")

    async def check_transactions_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        transactions = check_transactions_auto(context)
        
        if not transactions:
            await update.message.reply_text("No unreviewed transactions found.")
            return

    async def check_transactions_auto(context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.info("Polling for new transactions...")
        transactions = lunch.get_transactions(status='uncleared', pending=False)
        
        for transaction in transactions:
            if transaction.id in already_sent_transactions:
                logger.warn(f"Ignoring already sent transaction: {transaction.id}")
                continue
            already_sent_transactions.append(transaction.id)
            await send_transaction_message(context, transaction, '378659027')

        return transactions

    async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        logger.info(f"Button pressed: {query.data}")

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
            return await show_categories(lunch, update)
        
        if query.data.startswith("subcategorize"):
            return await show_subcategories(lunch, update)
        
        if query.data.startswith("applyCategory"):
            return await apply_category(lunch, update, context)
        
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

    async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
        replying_to_msg_id = update.message.reply_to_message.message_id
        tx_id = context.bot_data.get(replying_to_msg_id, None)
        if tx_id:
            logger.info(f"Setting notes to transaction ({tx_id}): {update.message.text}")
            lunch.update_transaction(tx_id, TransactionUpdateObject(notes=update.message.text))
            note_msg_id = update.message.message_id
            await context.bot.set_message_reaction(
                chat_id=update.message.chat_id,
                message_id=note_msg_id,
                reaction=ReactionEmoji.BANANA,
            )
        else:
            logger.error("No transaction ID found in bot data")


    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check_transactions", check_transactions_manual))
    application.add_handler(CallbackQueryHandler(button_callback))

    job_queue = application.job_queue
    job_queue.run_repeating(check_transactions_auto, interval=1800, first=5)

    application.add_handler(MessageHandler(filters.TEXT & filters.REPLY, handle_reply))

    logger.info("Telegram handlers set up successfully")

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

# TODO add menu to manually check transactions
#      figure out persistent storage and multiplexing
#      add button to trigger plaid transactions
#      add a button to show all pending txs
#      get state of current budget