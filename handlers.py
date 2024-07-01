from datetime import datetime
import logging
from lunchable import LunchMoney, TransactionUpdateObject
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ReactionEmoji

from budget_messaging import (
    hide_budget_categories,
    send_budget,
    show_budget_categories,
    show_bugdget_for_category,
)
from tx_messaging import send_plaid_details, send_transaction_message

logger = logging.getLogger("handlers")


async def handle_show_categories(lunch: LunchMoney, update: Update):
    """Updates the message to show the parent categories available"""
    query = update.callback_query
    transaction_id = int(query.data.split("_")[1])

    categories = lunch.get_categories()
    category_buttons = []
    for category in categories:
        if category.group_id is None:
            category_buttons.append(
                InlineKeyboardButton(
                    category.name,
                    callback_data=f"subcategorize_{transaction_id}_{category.id}",
                )
            )
    category_buttons = [
        category_buttons[i : i + 3] for i in range(0, len(category_buttons), 3)
    ]
    category_buttons.append(
        [
            InlineKeyboardButton(
                "Cancel", callback_data=f"cancelCategorization_{transaction_id}"
            )
        ]
    )

    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(category_buttons)
    )


async def handle_show_subcategories(lunch: LunchMoney, update: Update):
    """Updates the transaction with the selected category."""
    query = update.callback_query
    transaction_id, category_id = query.data.split("_")[1:]

    subcategories = lunch.get_categories()
    subcategory_buttons = []
    for subcategory in subcategories:
        if str(subcategory.group_id) == str(category_id):
            subcategory_buttons.append(
                InlineKeyboardButton(
                    subcategory.name,
                    callback_data=f"applyCategory_{transaction_id}_{subcategory.id}",
                )
            )
    subcategory_buttons = [
        subcategory_buttons[i : i + 3] for i in range(0, len(subcategory_buttons), 3)
    ]
    subcategory_buttons.append(
        [
            InlineKeyboardButton(
                "Cancel", callback_data=f"cancelCategorization_{transaction_id}"
            )
        ]
    )

    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(subcategory_buttons)
    )


async def handle_apply_category(
    lunch: LunchMoney, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Updates the transaction with the selected category."""
    query = update.callback_query
    chat_id = query.message.chat.id

    transaction_id, category_id = query.data.split("_")[1:]
    lunch.update_transaction(
        transaction_id, TransactionUpdateObject(category_id=category_id)
    )
    logger.info(f"Changing category for tx {transaction_id} to {category_id}")
    updated_transaction = lunch.get_transaction(transaction_id)
    logger.info(f"Updated transaction: {updated_transaction}")
    await send_transaction_message(
        context, updated_transaction, chat_id, query.message.message_id
    )


async def handle_dump_plaid_details(
    lunch: LunchMoney, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Sends a new message with the plaid metadata of the transaction."""
    query = update.callback_query
    transaction_id = int(query.data.split("_")[1])

    transaction = lunch.get_transaction(transaction_id)
    plaid_metadata = transaction.plaid_metadata
    plaid_details = f"*Plaid Metadata*\n\n"
    for key, value in plaid_metadata.items():
        if value is not None:
            plaid_details += f"*{key}:* `{value}`\n"

    chat_id = query.message.chat.id
    await send_plaid_details(query, context, chat_id, transaction_id, plaid_details)


async def handle_mark_tx_as_reviewed(lunch: LunchMoney, update: Update):
    """Updates the transaction status to reviewed."""
    query = update.callback_query
    transaction_id = int(query.data.split("_")[1])
    try:
        lunch.update_transaction(
            transaction_id, TransactionUpdateObject(status="cleared")
        )
        await query.edit_message_reply_markup(
            reply_markup=None
        )  # Remove the inline keyboard (button)
    except Exception as e:
        await query.edit_message_text(text=f"Error updating transaction: {str(e)}")


async def handle_set_tx_notes_or_tags(
    lunch: LunchMoney, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Updates the transaction notes."""
    replying_to_msg_id = update.message.reply_to_message.message_id
    tx_id = context.bot_data.get(replying_to_msg_id, None)

    if tx_id is None:
        logger.error("No transaction ID found in bot data")
        return

    msg_text = update.message.text
    message_are_tags = True
    for word in msg_text.split(" "):
        if not word.startswith("#"):
            message_are_tags = False
            break

    if message_are_tags:
        tags_without_hashtag = [
            tag[1:] for tag in msg_text.split(" ") if tag.startswith("#")
        ]
        logger.info(f"Setting tags to transaction ({tx_id}): {tags_without_hashtag}")
        lunch.update_transaction(
            tx_id, TransactionUpdateObject(tags=tags_without_hashtag)
        )
    else:
        logger.info(f"Setting notes to transaction ({tx_id}): {msg_text}")
        lunch.update_transaction(tx_id, TransactionUpdateObject(notes=msg_text))

    await context.bot.set_message_reaction(
        chat_id=update.message.chat_id,
        message_id=update.message.message_id,
        reaction=ReactionEmoji.WRITING_HAND,
    )


def get_default_budget(lunch: LunchMoney):
    """Get the budget for the current month."""
    # get a datetime of the first day of the current month
    first_day_current_month = datetime.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    # get a datetime of the current day
    current_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    return lunch.get_budgets(start_date=first_day_current_month, end_date=current_day)


async def handle_show_budget(
    lunch: LunchMoney, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Sends a message with the current budget."""
    budget = get_default_budget(lunch)
    await send_budget(update, context, budget)


async def handle_show_budget_categories(
    lunch: LunchMoney, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Updates the message to show the budget categories available."""
    budget = get_default_budget(lunch)
    await show_budget_categories(update, context, budget)


async def handle_hide_budget_categories(lunch: LunchMoney, update: Update):
    """Updates the message to hide the budget categories."""
    budget = get_default_budget(lunch)
    await hide_budget_categories(update, budget)


async def handle_show_budget_for_category(
    lunch: LunchMoney, update: Update, category_id: int
):
    """Updates the message to show the budget for a specific category"""
    all_budget = get_default_budget(lunch)

    # get super category
    category = lunch.get_category(category_id)
    children_categories_ids = [child.id for child in category.children]

    sub_budget = []
    for budget_item in all_budget:
        if budget_item.category_id in children_categories_ids:
            sub_budget.append(budget_item)

    await show_bugdget_for_category(update, all_budget, sub_budget)
