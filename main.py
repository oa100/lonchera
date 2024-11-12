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


from handlers.balances import handle_btn_accounts_balances, handle_show_balances
from handlers.budget import (
    handle_btn_hide_budget_categories,
    handle_btn_show_budget_categories,
    handle_btn_show_budget_for_category,
    handle_show_budget,
)
from handlers.general import (
    clear_cache,
    handle_errors,
    handle_generic_message,
    handle_start,
)
from handlers.transactions import (
    check_pending_transactions,
    handle_btn_apply_category,
    handle_btn_autocategorize,
    handle_btn_cancel_categorization,
    handle_btn_collapse_transaction,
    handle_btn_dump_plaid_details,
    handle_btn_mark_tx_as_reviewed,
    handle_btn_mark_tx_as_unreviewed,
    handle_btn_show_categories,
    handle_btn_show_subcategories,
    handle_btn_skip_transaction,
    handle_check_transactions,
    handle_edit_notes,
    handle_expand_tx_options,
    handle_rename_payee,
    handle_set_tags,
    handle_set_tx_notes_or_tags,
    poll_transactions_on_schedule,
)
from manual_tx import setup_manual_tx_handler
from handlers.settings import (
    handle_btn_change_poll_interval,
    handle_btn_done_settings,
    handle_btn_toggle_auto_mark_reviewed,
    handle_btn_toggle_poll_pending,
    handle_btn_toggle_show_datetime,
    handle_btn_toggle_tagging,
    handle_btn_trigger_plaid_refresh,
    handle_logout,
    handle_logout_cancel,
    handle_logout_confirm,
    handle_register_token,
    handle_btn_set_token_from_button,
    handle_settings,
)

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("lonchera")

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.ExtBot").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)


def setup_handlers(config):
    app = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()

    async def handle_unknown_btn(update: Update, _: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer(text=f"Unknown command {query.data}", show_alert=True)

    setup_manual_tx_handler(app, config)

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("register", handle_register_token))
    app.add_handler(CommandHandler("review_transactions", handle_check_transactions))
    app.add_handler(CommandHandler("pending_transactions", check_pending_transactions))
    app.add_handler(CommandHandler("show_budget", handle_show_budget))
    app.add_handler(CommandHandler("clear_cache", clear_cache))
    app.add_handler(CommandHandler("settings", handle_settings))
    app.add_handler(
        CallbackQueryHandler(handle_btn_skip_transaction, pattern=r"^skip_")
    )
    app.add_handler(
        CallbackQueryHandler(handle_btn_collapse_transaction, pattern=r"^collapse_")
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
        CallbackQueryHandler(
            handle_btn_toggle_auto_mark_reviewed, pattern=r"^toggleAutoMarkReviewed"
        )
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
        CallbackQueryHandler(handle_btn_autocategorize, pattern=r"^autocategorize_")
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

    app.add_handler(CommandHandler("balances", handle_show_balances))
    app.add_handler(
        CallbackQueryHandler(
            handle_btn_accounts_balances, pattern=r"^accountsBalances_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            handle_btn_trigger_plaid_refresh, pattern=r"^triggerPlaidRefresh$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            handle_btn_toggle_poll_pending, pattern=r"^togglePollPending"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            handle_btn_toggle_show_datetime, pattern=r"^toggleShowDateTime"
        )
    )

    app.add_handler(
        CallbackQueryHandler(handle_btn_toggle_tagging, pattern=r"^toggleTagging")
    )

    app.add_handler(CallbackQueryHandler(handle_unknown_btn))

    app.add_error_handler(handle_errors)

    app.job_queue.run_repeating(poll_transactions_on_schedule, interval=60, first=5)

    app.add_handler(
        MessageHandler(filters.TEXT & filters.REPLY, handle_set_tx_notes_or_tags)
    )
    app.add_handler(MessageHandler(filters.TEXT, handle_generic_message))

    logger.info("Telegram handlers set up successfully")

    return app


def load_config():
    load_dotenv()

    return {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
        "PROMPT_FOR_NOTES": os.getenv("PROMPT_FOR_NOTES", "true").lower() == "true",
        "PROMPT_FOR_CATEGORIES": os.getenv("PROMPT_FOR_CATEGORIES", "true").lower()
        == "true",
    }


def main():
    config = load_config()
    application = setup_handlers(config)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

# TODO
# - Add custom icons for famous merchants
# - Add some settings to disable part of the add manual transaction flow
# - Add command to resync transactions. i.e., if a change was made to the transaction in Lunch Money,
#   it should be reflected in the bot after this is run. It should just go through all the messages
#   sent and for each one get the transaction from Lunch Money and update the message.
#
