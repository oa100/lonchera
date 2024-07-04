from datetime import datetime, timedelta
import logging
import os
from typing import List, Union

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

from handlers.general import (
    handle_apply_category,
    handle_dump_plaid_details,
    handle_errors,
    handle_generic_message,
    handle_hide_budget_categories,
    handle_mark_unreviewed,
    handle_show_budget,
    handle_show_budget_categories,
    handle_show_budget_for_category,
    handle_mark_tx_as_reviewed,
    handle_set_tx_notes_or_tags,
    handle_show_categories,
    handle_show_subcategories,
    handle_start,
)
from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from handlers.settings import (
    handle_change_poll_interval,
    handle_done_settings,
    handle_register_token,
    handle_set_token_from_button,
    handle_settings,
)
from tx_messaging import get_tx_buttons, send_transaction_message
from utils import find_related_tx

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("lonchera")

httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)


def setup_handlers(config):
    application = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()

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
            chat_id=update.message.chat_id,
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
        context: ContextTypes.DEFAULT_TYPE, chat_id: Union[str, int]
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
        chat_id: Union[str, int],
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
        transactions = [
            tx for tx in transactions if tx.is_pending == True and tx.notes == None
        ]

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

        for (chat_id,) in chat_ids:
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
            return await handle_show_budget_categories(update, context)

        if query.data.startswith("exitBudgetDetails"):
            return await handle_hide_budget_categories(update)

        if query.data.startswith("showBudgetDetails"):
            category_id = int(query.data.split("_")[1])
            return await handle_show_budget_for_category(update, category_id)

        if query.data.startswith("changePollInterval"):
            return await handle_change_poll_interval(update, context)

        if query.data == "registerToken":
            return await handle_set_token_from_button(update, context)

        if query.data == "doneSettings":
            return await handle_done_settings(update, context)

        if query.data.startswith("cancelCategorization"):
            transaction_id = int(query.data.split("_")[1])
            await query.edit_message_reply_markup(
                reply_markup=get_tx_buttons(transaction_id)
            )
            return

        if query.data.startswith("categorize"):
            return await handle_show_categories(update)

        if query.data.startswith("subcategorize"):
            return await handle_show_subcategories(update)

        if query.data.startswith("applyCategory"):
            return await handle_apply_category(update, context)

        if query.data.startswith("plaid"):
            return await handle_dump_plaid_details(update, context)

        if query.data.startswith("review"):
            return await handle_mark_tx_as_reviewed(update)

        await context.bot.send_message(
            chat_id=chat_id, text=f"Unknown command {query.data}"
        )

    async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await handle_set_tx_notes_or_tags(update, context)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register_token))
    application.add_handler(
        CommandHandler("review_transactions", check_transactions_manual)
    )
    application.add_handler(
        CommandHandler("pending_transactions", check_pending_transactions)
    )
    application.add_handler(CommandHandler("refresh", trigger_plaid_refresh))
    application.add_handler(CommandHandler("show_budget", get_budget))
    application.add_handler(CommandHandler("clear_cache", clear_cache))
    application.add_handler(CommandHandler("mark_unreviewed", mark_unreviewed))
    application.add_handler(CommandHandler("settings", handle_settings))
    application.add_handler(CallbackQueryHandler(button_callback))

    application.add_error_handler(handle_errors)

    job_queue = application.job_queue
    job_queue.run_repeating(poll_transactions_on_schedule, interval=60, first=5)

    application.add_handler(MessageHandler(filters.TEXT & filters.REPLY, handle_reply))
    application.add_handler(MessageHandler(filters.TEXT, handle_generic_message))

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
#  List budget from last month
# Add settings command:
# - Delete all data
#    maybe use the keyboard markup
# Refactor settings logic into its own file
# Move handlers to their own file, and all handlers to a handlers folder
# Use: CallbackQueryHandler https://chatgpt.com/c/f9a7b05c-44a3-4a9b-8cf5-729edbc4685b
