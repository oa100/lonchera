from datetime import datetime, timedelta
import logging
import os
from typing import List

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.constants import ReactionEmoji

from lunchable import LunchMoney
from lunchable.models import TransactionObject

from handlers import (
    handle_apply_category,
    handle_dump_plaid_details,
    handle_hide_budget_categories,
    handle_show_budget,
    handle_show_budget_categories,
    handle_show_budget_for_category,
    handle_mark_tx_as_reviewed,
    handle_set_tx_notes_or_tags,
    handle_show_categories,
    handle_show_subcategories,
)
from persistence import Persistence
from tx_messaging import get_tx_buttons, send_transaction_message

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("lonchera")

httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)

db_path = "transactions.db"
db = Persistence(db_path)


def setup_handlers(config):
    application = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()

    lunch = LunchMoney(access_token=config["LUNCH_MONEY_TOKEN"])

    async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "Bot started. Will start polling for new transactions soon."
        )

    async def check_transactions_manual(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        transactions = await check_transactions_and_telegram_them(context)

        if not transactions:
            await update.message.reply_text("No unreviewed transactions found.")
            return

    async def check_pending_transactions(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        transactions = await check_transactions_and_telegram_them(
            context, pending=True, ignore_already_sent=False
        )

        if not transactions:
            await update.message.reply_text("No pending transactions found.")
            return

    async def trigger_plaid_refresh(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        lunch.trigger_fetch_from_plaid()
        await context.bot.set_message_reaction(
            chat_id=update.message.chat_id,
            message_id=update.message.message_id,
            reaction=ReactionEmoji.HANDSHAKE,
        )

    async def get_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await handle_show_budget(lunch, update, context)

    async def clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        db.nuke()
        await context.bot.set_message_reaction(
            chat_id=update.message.chat_id,
            message_id=update.message.message_id,
            reaction=ReactionEmoji.THUMBS_UP,
        )

    async def check_transactions_and_telegram_them(
        context: ContextTypes.DEFAULT_TYPE, pending=False, ignore_already_sent=True
    ) -> List[TransactionObject]:
        # get date from 15 days ago
        two_weeks_ago = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=15)
        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        logger.info(f"Polling for new transactions from {two_weeks_ago} to {now}...")

        if pending:
            transactions = lunch.get_transactions(
                pending=True, start_date=two_weeks_ago, end_date=now
            )
            logger.info(f"Found {len(transactions)} pending transactions")
            transactions = [
                tx for tx in transactions if tx.is_pending == True and tx.notes == None
            ]
        else:
            transactions = lunch.get_transactions(
                status="uncleared",
                pending=pending,
                start_date=two_weeks_ago,
                end_date=now,
            )

        logger.info(f"Found {len(transactions)} transactions (pending={pending})")

        for transaction in transactions:
            if ignore_already_sent and db.already_sent(transaction.id):
                logger.warn(f"Ignoring already sent transaction: {transaction.id}")
                continue
            msg_id = await send_transaction_message(context, transaction, "378659027")
            db.mark_as_sent(transaction.id, msg_id)

        return transactions

    async def button_callback(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        logger.info(f"Button pressed: {query.data}")

        chat_id = query.message.chat.id
        await query.answer()

        if query.data.startswith("skip"):
            await query.edit_message_reply_markup(reply_markup=None)
            return

        if query.data.startswith("showBudgetCategories"):
            return await handle_show_budget_categories(lunch, update, context)

        if query.data.startswith("exitBudgetDetails"):
            return await handle_hide_budget_categories(lunch, update)

        if query.data.startswith("showBudgetDetails"):
            category_id = int(query.data.split("_")[1])
            return await handle_show_budget_for_category(lunch, update, category_id)

        transaction_id = int(query.data.split("_")[1])

        if query.data.startswith("cancelCategorization"):
            await query.edit_message_reply_markup(
                reply_markup=get_tx_buttons(transaction_id)
            )
            return

        if query.data.startswith("categorize"):
            return await handle_show_categories(lunch, update)

        if query.data.startswith("subcategorize"):
            return await handle_show_subcategories(lunch, update)

        if query.data.startswith("applyCategory"):
            return await handle_apply_category(lunch, update, context)

        if query.data.startswith("plaid"):
            return await handle_dump_plaid_details(lunch, update, context)

        if query.data.startswith("review"):
            return await handle_mark_tx_as_reviewed(lunch, update)

        await context.bot.send_message(
            chat_id=chat_id, text=f"Unknown command {query.data}"
        )

    async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await handle_set_tx_notes_or_tags(update, context, lunch, db)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        CommandHandler("review_transactions", check_transactions_manual)
    )
    application.add_handler(
        CommandHandler("pending_transactions", check_pending_transactions)
    )
    application.add_handler(CommandHandler("refresh", trigger_plaid_refresh))
    application.add_handler(CommandHandler("show_budget", get_budget))
    application.add_handler(CommandHandler("clear_cache", clear_cache))
    application.add_handler(CallbackQueryHandler(button_callback))

    job_queue = application.job_queue
    job_queue.run_repeating(
        check_transactions_and_telegram_them, interval=1800, first=5
    )

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

# TODO
#      persistence should inlcude chat_id
#      remove hardcoded chat_id
#      allow specifying lunch money api key from bot
