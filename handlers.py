import logging
from lunchable import LunchMoney, TransactionUpdateObject
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ReactionEmoji

from messaging import send_plaid_details, send_transaction_message

logger = logging.getLogger('handlers')


async def show_categories(lunch: LunchMoney, update: Update):
    """Updates the message to show the parent categories available"""
    query = update.callback_query
    transaction_id = int(query.data.split("_")[1])

    categories = lunch.get_categories()
    category_buttons = []
    for category in categories:
        if category.group_id is None:
            category_buttons.append(InlineKeyboardButton(category.name, callback_data=f"subcategorize_{transaction_id}_{category.id}"))
    category_buttons = [category_buttons[i:i + 3] for i in range(0, len(category_buttons), 3)]
    category_buttons.append([InlineKeyboardButton("Cancel", callback_data=f"cancelCategorization_{transaction_id}")])

    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(category_buttons))


async def show_subcategories(lunch: LunchMoney, update: Update):
    """Updates the transaction with the selected category."""
    query = update.callback_query
    transaction_id, category_id = query.data.split("_")[1:]

    subcategories = lunch.get_categories()
    subcategory_buttons = []
    for subcategory in subcategories:
        if str(subcategory.group_id) == str(category_id):
            subcategory_buttons.append(InlineKeyboardButton(subcategory.name, callback_data=f"applyCategory_{transaction_id}_{subcategory.id}"))
    subcategory_buttons = [subcategory_buttons[i:i + 3] for i in range(0, len(subcategory_buttons), 3)]
    subcategory_buttons.append([InlineKeyboardButton("Cancel", callback_data=f"cancelCategorization_{transaction_id}")])
    
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(subcategory_buttons))


async def apply_category(lunch: LunchMoney, update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id

    transaction_id, category_id = query.data.split("_")[1:]
    lunch.update_transaction(transaction_id, TransactionUpdateObject(category_id=category_id))
    updated_transaction = lunch.get_transaction(transaction_id)
    await send_transaction_message(context, updated_transaction, chat_id, query.message.message_id)


async def dump_plaid_details(lunch: LunchMoney, update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def mark_tx_as_reviewed(lunch: LunchMoney, update: Update):
    query = update.callback_query
    transaction_id = int(query.data.split("_")[1])
    try:
        lunch.update_transaction(transaction_id, TransactionUpdateObject(status='cleared'))
        await query.edit_message_reply_markup(reply_markup=None) # Remove the inline keyboard (button)
    except Exception as e:
        await query.edit_message_text(text=f"Error updating transaction: {str(e)}")


async def set_tx_notes(lunch: LunchMoney, update: Update, context: ContextTypes.DEFAULT_TYPE):
    replying_to_msg_id = update.message.reply_to_message.message_id
    tx_id = context.bot_data.get(replying_to_msg_id, None)
    if tx_id:
        logger.info(f"Setting notes to transaction ({tx_id}): {update.message.text}")
        lunch.update_transaction(tx_id, TransactionUpdateObject(notes=update.message.text))
        note_msg_id = update.message.message_id
        await context.bot.set_message_reaction(
            chat_id=update.message.chat_id,
            message_id=note_msg_id,
            reaction=ReactionEmoji.WRITING_HAND,
        )
    else:
        logger.error("No transaction ID found in bot data")