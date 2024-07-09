import logging
from textwrap import dedent
from lunchable import TransactionInsertObject
from telegram import Update
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    Application,
)
from telegram.constants import ParseMode
import datetime

from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from tx_messaging import send_transaction_message
from utils import Keyboard, make_tag

# Conversation states
(
    DATE,
    CATEGORY_GROUP,
    CATEGORY,
    PAYEE,
    AMOUNT,
    CURRENCY,
    NOTES,
    ACCOUNT,
    CONFIRM,
) = range(9)

# Define callback data
TODAY, YESTERDAY = "today", "yesterday"
USD, COP = "USD", "COP"
CREDIT, DEBIT, CASH = "credit", "debit", "cash"
SKIP = "skip"
SPENT_MONEY = "spent"
RECEIVED_MONEY = "received"
CANCEL = "cancel"


logger = logging.getLogger("manual_tx")


def get_transaction_state_message(
    context: ContextTypes.DEFAULT_TYPE, extra_info: str = ""
):
    date = context.user_data.get("date", "N/A")
    category = context.user_data.get("category", None)
    if category is None:
        category = "None selected"
    else:
        category = make_tag(category)
    payee = context.user_data.get("payee", "N/A")
    amount = context.user_data.get("amount", "0.0")
    amount = float(amount)
    currency = context.user_data.get("currency", "USD")
    notes = context.user_data.get("notes", "N/A")
    account = context.user_data.get("account", "N/A")

    result = dedent(
        f"""
        *Manual transaction form*

        *Date*: {date}
        *Category*: {category}
        *Payee*: {payee}
        *Amount*: {amount:,.2f} {currency}
        *Notes*: {notes}
        *Account*: {account}
        """
    )

    if extra_info:
        result += f"\n\n{extra_info}"

    return result


async def start_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kbd = Keyboard()
    kbd += ("Today", TODAY)
    kbd += ("Yesterday", YESTERDAY)
    kbd += ("Cancel", CANCEL)
    msg_ctx = await update.message.reply_text(
        text=dedent(
            """
            *Manual transaction form*

            I will be asking your for the basic information of your transaction.

            Let's start by typing the date (format: `YYYY-MM-DD`) or select an option:
            """
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kbd.build(),
    )
    context.user_data["add_tx_msg_id"] = msg_ctx.message_id
    return DATE


async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

        if query.data in [TODAY, YESTERDAY]:
            date = (
                datetime.date.today()
                if query.data == TODAY
                else datetime.date.today() - datetime.timedelta(days=1)
            )
            context.user_data["date"] = date.strftime("%Y-%m-%d")
    else:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
        )
        try:
            # validate date to make sure it's in the right format
            datetime.datetime.strptime(update.message.text, "%Y-%m-%d")
            context.user_data["date"] = update.message.text
        except ValueError:
            kbd = Keyboard()
            kbd += ("Today", TODAY)
            kbd += ("Yesterday", YESTERDAY)
            kbd += ("Cancel", CANCEL)
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["add_tx_msg_id"],
                text=dedent(
                    f"""
                    *Manual transaction form*

                    Invalid date (`{update.message.text}`).

                    Please enter the date in the format `YYYY-MM-DD` or select an option:
                    """
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kbd.build(),
            )

            return DATE

    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
    categories = lunch.get_categories()
    kbd = Keyboard()
    for category in categories:
        if category.group_id is None:
            kbd += (category.name, f"subcategory_{category.id}")

    kbd += ("Cancel", CANCEL)

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data["add_tx_msg_id"],
        text=get_transaction_state_message(context, "Please select a category:"),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kbd.build(),
    )
    return CATEGORY_GROUP


async def get_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    category_group_id = query.data.split("_")[1]
    context.user_data["category_group"] = category_group_id

    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
    subcategories = lunch.get_categories()
    kbd = Keyboard()
    for subcategory in subcategories:
        if str(subcategory.group_id) == str(category_group_id):
            kbd += (subcategory.name, f"subcategory_{subcategory.id}")

    kbd += ("Cancel", CANCEL)

    await query.edit_message_text(
        text=get_transaction_state_message(context, "Please select a subcategory:"),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kbd.build(),
    )
    return CATEGORY


async def get_payee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    category_id = query.data.split("_")[1]
    context.user_data["category_id"] = category_id

    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
    category = lunch.get_category(category_id)
    context.user_data["category"] = category.name

    await query.edit_message_text(
        text=get_transaction_state_message(
            context, "Enter the name of the merchant or payee:"
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboard.build_from(("Cancel", CANCEL)),
    )
    return PAYEE


async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["payee"] = update.message.text
    await context.bot.delete_message(
        chat_id=update.effective_chat.id, message_id=update.message.message_id
    )

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data["add_tx_msg_id"],
        text=get_transaction_state_message(
            context,
            "Enter the transaction amount (defaults to USD but you can specify the currency like this: `5000 cop`):",
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboard.build_from(("Cancel", CANCEL)),
    )
    return AMOUNT


async def get_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = update.message.text
    if " " in amount:
        amount, currency = amount.split(" ")

        # make sure currency is a three letters string
        if len(currency) != 3:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["add_tx_msg_id"],
                text=get_transaction_state_message(
                    context,
                    dedent(
                        f"""
                        Invalid currency (`{currency}`). It must be a three letters string (e.g. `USD`).

                        Please enter the transaction amount (defaults to USD but you can specify the currency like this: `5000 cop`):
                        """
                    ),
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=Keyboard.build_from(("Cancel", CANCEL)),
            )

            await context.bot.delete_message(
                chat_id=update.effective_chat.id, message_id=update.message.message_id
            )
            return AMOUNT

        context.user_data["currency"] = currency.upper()

    # validate amount to make sure it's a number
    try:
        float(amount)
    except ValueError:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data["add_tx_msg_id"],
            text=get_transaction_state_message(
                context,
                dedent(
                    f"""
                    Invalid amount (`{amount}`). It must be a number (e.g. `42.5`).

                    Please enter the transaction amount (defaults to USD but you can specify the currency like this: `5000 cop`):
                    """
                ),
            ),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboard.build_from(("Cancel", CANCEL)),
        )
        context.user_data["currency"] = None

        await context.bot.delete_message(
            chat_id=update.effective_chat.id, message_id=update.message.message_id
        )
        return AMOUNT

    context.user_data["amount"] = amount

    await context.bot.delete_message(
        chat_id=update.effective_chat.id, message_id=update.message.message_id
    )
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data["add_tx_msg_id"],
        text=get_transaction_state_message(
            context,
            "Enter any notes (optional):",
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboard.build_from(("Skip", SKIP), ("Cancel", CANCEL)),
    )
    return NOTES


async def get_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # get all the assets accounts
    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
    assets = lunch.get_assets()

    only_accounts = [
        asset
        for asset in assets
        if asset.type_name == "credit" or asset.type_name == "cash"
    ]

    kbd = Keyboard()
    for acct in only_accounts:
        kbd += (f"{acct.display_name or acct.name}", f"account_{acct.id}")
    kbd += ("Cancel", CANCEL)

    query = update.callback_query
    if query:
        await query.answer()

        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data["add_tx_msg_id"],
            text=get_transaction_state_message(
                context,
                "Select the account:",
            ),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kbd.build(),
        )
        return ACCOUNT
    context.user_data["notes"] = update.message.text
    await context.bot.delete_message(
        chat_id=update.effective_chat.id, message_id=update.message.message_id
    )
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data["add_tx_msg_id"],
        text=get_transaction_state_message(
            context,
            "Select the account:",
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kbd.build(),
    )
    return ACCOUNT


async def confirm_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    account_id = query.data.split("_")[1]
    context.user_data["account_id"] = account_id

    # get asset name
    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
    assets = lunch.get_assets()
    account = next((asset for asset in assets if asset.id == int(account_id)), None)

    if account:
        context.user_data["account"] = account.display_name or account.name

    await query.answer()

    await query.edit_message_text(
        text=get_transaction_state_message(context),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboard.build_from(
            ("I spent this money", SPENT_MONEY),
            ("I received this money", RECEIVED_MONEY),
            ("Cancel", CANCEL),
        ),
    )
    return CONFIRM


async def save_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data == RECEIVED_MONEY:
        context.user_data["amount"] = "-" + context.user_data["amount"]

    transaction_data = context.user_data
    logger.info(f"Transaction data: {transaction_data}")

    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
    tx_ids = lunch.insert_transactions(
        TransactionInsertObject(
            date=datetime.datetime.strptime(transaction_data["date"], "%Y-%m-%d"),
            category_id=transaction_data["category_id"],
            payee=transaction_data["payee"],
            amount=float(transaction_data["amount"]),
            currency=transaction_data.get("currency", "USD").lower(),
            notes=transaction_data.get("notes", None),
            status="cleared",
            asset_id=int(transaction_data["account_id"]),
        )
    )

    # poll the transaction we just created
    [transaction_id] = tx_ids
    transaction = lunch.get_transaction(transaction_id)

    await query.answer("Transaction saved successfully!", show_alert=True)

    msg_id = await send_transaction_message(
        context,
        transaction=transaction,
        chat_id=update.effective_chat.id,
        message_id=context.user_data["add_tx_msg_id"],
    )
    get_db().mark_as_sent(
        transaction.id, update.effective_chat.id, msg_id, transaction.recurring_type
    )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.delete_message(
        chat_id=update.effective_chat.id,
        message_id=context.user_data["add_tx_msg_id"],
    )
    context.user_data["add_tx_msg_id"] = None
    return ConversationHandler.END


def setup_manual_tx_handler(app: Application):
    transaction_handler = ConversationHandler(
        entry_points=[CommandHandler("add_transaction", start_transaction)],
        states={
            DATE: [
                CallbackQueryHandler(cancel, pattern=CANCEL),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_category),
                CallbackQueryHandler(get_category),
            ],
            CATEGORY_GROUP: [
                CallbackQueryHandler(cancel, pattern=CANCEL),
                CallbackQueryHandler(get_subcategory),
            ],
            CATEGORY: [
                CallbackQueryHandler(cancel, pattern=CANCEL),
                CallbackQueryHandler(get_payee),
            ],
            PAYEE: [
                CallbackQueryHandler(cancel, pattern=CANCEL),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount),
            ],
            AMOUNT: [
                CallbackQueryHandler(cancel, pattern=CANCEL),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_notes),
                CallbackQueryHandler(get_notes),
            ],
            NOTES: [
                CallbackQueryHandler(cancel, pattern=CANCEL),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_account),
                CallbackQueryHandler(get_account),
            ],
            ACCOUNT: [
                CallbackQueryHandler(cancel, pattern=CANCEL),
                CallbackQueryHandler(confirm_transaction),
            ],
            CONFIRM: [
                CallbackQueryHandler(cancel, pattern=CANCEL),
                CallbackQueryHandler(save_transaction, pattern=SPENT_MONEY),
                CallbackQueryHandler(save_transaction, pattern=RECEIVED_MONEY),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern=CANCEL),
        ],
    )

    app.add_handler(transaction_handler)
