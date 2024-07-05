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

from lunchable.models import TransactionObject

from handlers.budget import (
    handle_btn_hide_budget_categories,
    handle_btn_show_budget_categories,
    handle_btn_show_budget_for_category,
    handle_show_budget,
)
from handlers.general import (
    handle_errors,
    handle_generic_message,
    handle_start,
)
from handlers.transactions import (
    handle_btn_apply_category,
    handle_btn_cancel_categorization,
    handle_btn_dump_plaid_details,
    handle_btn_mark_tx_as_reviewed,
    handle_btn_show_categories,
    handle_btn_show_subcategories,
    handle_btn_skip_transaction,
    handle_mark_unreviewed,
    handle_set_tx_notes_or_tags,
)
from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from handlers.settings import (
    handle_btn_change_poll_interval,
    handle_btn_done_settings,
    handle_register_token,
    handle_btn_set_token_from_button,
    handle_settings,
)
from tx_messaging import send_transaction_message
from utils import find_related_tx, get_chat_id

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("lonchera")

httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)


def setup_handlers(config):
    app = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()

    # lunch = LunchMoney(access_token=config["LUNCH_MONEY_TOKEN"])

    async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await handle_start(update)

    async def register_token(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await handle_register_token(update, context)

    async def check_transactions_manual(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        transactions = await check_transactions_and_telegram_them(
            context, chat_id=update.message.chat_id
        )

        if not transactions:
            await update.message.reply_text("No unreviewed transactions found.")
            return

    async def check_pending_transactions(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        transactions = await check_pending_transactions_and_telegram_them(
            context,
            chat_id=get_chat_id(update),
        )

        if not transactions:
            await update.message.reply_text("No pending transactions found.")
            return

    async def trigger_plaid_refresh(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        lunch = get_lunch_client_for_chat_id(update.message.chat_id)
        lunch.trigger_fetch_from_plaid()
        await context.bot.set_message_reaction(
            chat_id=update.message.chat_id,
            message_id=update.message.message_id,
            reaction=ReactionEmoji.HANDSHAKE,
        )

    async def get_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await handle_show_budget(update, context)

    async def clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        get_db().nuke(update.message.chat_id)
        await context.bot.set_message_reaction(
            chat_id=update.message.chat_id,
            message_id=update.message.message_id,
            reaction=ReactionEmoji.THUMBS_UP,
        )

    async def mark_unreviewed(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await handle_mark_unreviewed(update, context)

    async def check_transactions_and_telegram_them(
        context: ContextTypes.DEFAULT_TYPE, chat_id: int
    ) -> List[TransactionObject]:
        # get date from 15 days ago
        two_weeks_ago = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=15)
        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        logger.info(f"Polling for new transactions from {two_weeks_ago} to {now}...")

        lunch = get_lunch_client_for_chat_id(chat_id)
        transactions = lunch.get_transactions(
            status="uncleared",
            pending=False,
            start_date=two_weeks_ago,
            end_date=now,
        )

        logger.info(f"Found {len(transactions)} unreviewed transactions")

        for transaction in transactions:
            if get_db().was_already_sent(transaction.id):
                logger.warning(f"Ignoring already sent transaction: {transaction.id}")
                continue

            # check if the current transaction is related to a previously sent one
            # like a payment to a credit card
            related_tx = find_related_tx(transaction, transactions)
            reply_msg_id = None
            if related_tx:
                logger.info(
                    f"Found related transaction {related_tx.id} for {transaction.id}"
                )
                reply_msg_id = get_db().get_message_id_associated_with(
                    related_tx.id, chat_id
                )

            msg_id = await send_transaction_message(
                context, transaction, chat_id, reply_to_message_id=reply_msg_id
            )
            get_db().mark_as_sent(transaction.id, chat_id, msg_id)

        return transactions

    async def check_pending_transactions_and_telegram_them(
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
    ) -> List[TransactionObject]:
        # get date from 15 days ago
        two_weeks_ago = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=15)
        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        logger.info(f"Polling for new transactions from {two_weeks_ago} to {now}...")

        lunch = get_lunch_client_for_chat_id(chat_id)
        transactions = lunch.get_transactions(
            pending=True, start_date=two_weeks_ago, end_date=now
        )
        logger.info(f"Found {len(transactions)} pending transactions")
        transactions = [tx for tx in transactions if tx.is_pending and tx.notes is None]

        logger.info(f"Found {len(transactions)} pending transactions")

        for transaction in transactions:
            msg_id = await send_transaction_message(context, transaction, chat_id)
            get_db().mark_as_sent(transaction.id, chat_id, msg_id, pending=True)

        return transactions

    async def poll_transactions_on_schedule(context: ContextTypes.DEFAULT_TYPE):
        """
        Gets called every minute to poll transactions for all registered chats.
        However, each chat can have its own polling settings, so we use this
        function to check the settings for each chat and decide whether to poll.
        """
        chat_ids = get_db().get_all_registered_chats()
        if len(chat_ids) is None:
            logger.info("No chats registered yet")

        for chat_id in chat_ids:
            settings = get_db().get_current_settings(chat_id)
            if not settings:
                logger.error(f"No settings found for chat {chat_id}!")
                continue

            # this is the last time we polled, saved as a string using:
            # datetime.now().isoformat()
            last_poll_at = settings["last_poll_at"]
            should_poll = False
            if last_poll_at is None:
                logger.info(f"First poll for chat {chat_id}")
                last_poll_at = datetime.now() - timedelta(days=1)
                should_poll = True
            else:
                last_poll_at = datetime.fromisoformat(last_poll_at)
                poll_interval_seconds = settings["poll_interval_secs"]
                next_poll_at = last_poll_at + timedelta(seconds=poll_interval_seconds)
                should_poll = datetime.now() >= next_poll_at

            if should_poll:
                await check_transactions_and_telegram_them(context, chat_id=chat_id)
                get_db().update_last_poll_at(chat_id, datetime.now().isoformat())

    async def handle_unknown_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer(text=f"Unknown command {query.data}", show_alert=True)

    async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await handle_set_tx_notes_or_tags(update, context)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register_token))
    app.add_handler(CommandHandler("review_transactions", check_transactions_manual))
    app.add_handler(CommandHandler("pending_transactions", check_pending_transactions))
    app.add_handler(CommandHandler("refresh", trigger_plaid_refresh))
    app.add_handler(CommandHandler("show_budget", get_budget))
    app.add_handler(CommandHandler("clear_cache", clear_cache))
    app.add_handler(CommandHandler("mark_unreviewed", mark_unreviewed))
    app.add_handler(CommandHandler("settings", handle_settings))
    app.add_handler(
        CallbackQueryHandler(handle_btn_skip_transaction, pattern=r"^skip$")
    )
    app.add_handler(
        CallbackQueryHandler(
            handle_btn_show_budget_categories, pattern=r"^showBudgetCategories$"
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            handle_btn_hide_budget_categories, pattern=r"^exitBudgetDetails$"
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            handle_btn_show_budget_for_category, pattern=r"^showBudgetDetails_"
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            handle_btn_change_poll_interval, pattern=r"^changePollInterval"
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            handle_btn_set_token_from_button, pattern=r"^registerToken$"
        )
    )
    app.add_handler(
        CallbackQueryHandler(handle_btn_done_settings, pattern=r"^doneSettings$")
    )
    app.add_handler(
        CallbackQueryHandler(
            handle_btn_cancel_categorization, pattern=r"^cancelCategorization_"
        )
    )
    app.add_handler(
        CallbackQueryHandler(handle_btn_show_categories, pattern=r"^categorize_")
    )
    app.add_handler(
        CallbackQueryHandler(handle_btn_show_subcategories, pattern=r"^subcategorize_")
    )
    app.add_handler(
        CallbackQueryHandler(handle_btn_apply_category, pattern=r"^applyCategory_")
    )
    app.add_handler(
        CallbackQueryHandler(handle_btn_dump_plaid_details, pattern=r"^plaid_")
    )
    app.add_handler(
        CallbackQueryHandler(handle_btn_mark_tx_as_reviewed, pattern=r"^review_")
    )
    app.add_handler(CallbackQueryHandler(handle_unknown_btn))

    app.add_error_handler(handle_errors)

    job_queue = app.job_queue
    job_queue.run_repeating(poll_transactions_on_schedule, interval=60, first=5)

    app.add_handler(MessageHandler(filters.TEXT & filters.REPLY, handle_reply))
    app.add_handler(MessageHandler(filters.TEXT, handle_generic_message))

    logger.info("Telegram handlers set up successfully")

    return app


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
# List budget from last month
# Add settings command:
# - Delete all data
#    maybe use the keyboard markup
# Use: CallbackQueryHandler https://chatgpt.com/c/f9a7b05c-44a3-4a9b-8cf5-729edbc4685b
