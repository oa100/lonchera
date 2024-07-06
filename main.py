import logging
import os

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
    handle_trigger_plaid_refresh,
)
from handlers.transactions import (
    check_pending_transactions,
    handle_btn_apply_category,
    handle_btn_cancel_categorization,
    handle_btn_dump_plaid_details,
    handle_btn_mark_tx_as_reviewed,
    handle_btn_mark_tx_as_unreviewed,
    handle_btn_show_categories,
    handle_btn_show_subcategories,
    handle_btn_skip_transaction,
    handle_check_transactions,
    handle_edit_notes,
    handle_expand_tx_options,
    handle_mark_unreviewed,
    handle_rename_payee,
    handle_set_tags,
    handle_set_tx_notes_or_tags,
    poll_transactions_on_schedule,
)
from persistence import get_db
from handlers.settings import (
    handle_btn_change_poll_interval,
    handle_btn_done_settings,
    handle_logout,
    handle_logout_cancel,
    handle_logout_confirm,
    handle_register_token,
    handle_btn_set_token_from_button,
    handle_settings,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("lonchera")

httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)


def setup_handlers(config):
    app = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()

    async def clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        get_db().nuke(update.message.chat_id)
        await context.bot.set_message_reaction(
            chat_id=update.message.chat_id,
            message_id=update.message.message_id,
            reaction=ReactionEmoji.THUMBS_UP,
        )

    async def handle_unknown_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer(text=f"Unknown command {query.data}", show_alert=True)

    async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await handle_set_tx_notes_or_tags(update, context)

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("register", handle_register_token))
    app.add_handler(CommandHandler("review_transactions", handle_check_transactions))
    app.add_handler(CommandHandler("pending_transactions", check_pending_transactions))
    app.add_handler(CommandHandler("refresh", handle_trigger_plaid_refresh))
    app.add_handler(CommandHandler("show_budget", handle_show_budget))
    app.add_handler(CommandHandler("clear_cache", clear_cache))
    app.add_handler(CommandHandler("mark_unreviewed", handle_mark_unreviewed))
    app.add_handler(CommandHandler("settings", handle_settings))
    app.add_handler(
        CallbackQueryHandler(handle_btn_skip_transaction, pattern=r"^skip_")
    )
    app.add_handler(
        CallbackQueryHandler(
            handle_btn_show_budget_categories, pattern=r"^showBudgetCategories_"
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            handle_btn_hide_budget_categories, pattern=r"^exitBudgetDetails_"
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            handle_btn_show_budget_for_category, pattern=r"^showBudgetDetails_"
        )
    )
    app.add_handler(CallbackQueryHandler(handle_show_budget, pattern=r"^showBudget_"))
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
    app.add_handler(CallbackQueryHandler(handle_logout, pattern=r"^logout$"))
    app.add_handler(
        CallbackQueryHandler(handle_logout_confirm, pattern=r"^logout_confirm$")
    )
    app.add_handler(
        CallbackQueryHandler(handle_logout_cancel, pattern=r"^logout_cancel$")
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
    app.add_handler(
        CallbackQueryHandler(handle_btn_mark_tx_as_unreviewed, pattern=r"^unreview_")
    )
    app.add_handler(
        CallbackQueryHandler(handle_expand_tx_options, pattern=r"^moreOptions_")
    )
    app.add_handler(CallbackQueryHandler(handle_rename_payee, pattern=r"^renamePayee_"))
    app.add_handler(CallbackQueryHandler(handle_edit_notes, pattern=r"^editNotes_"))
    app.add_handler(CallbackQueryHandler(handle_set_tags, pattern=r"^setTags_"))
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
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
    }


def main():
    config = load_config()
    application = setup_handlers(config)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

# TODO
# - Add option to show net worth
# - Add option to show balances
# - Add custom icons for famous merchants
# - keep just one connection around
