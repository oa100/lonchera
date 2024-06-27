from lunchable import TransactionUpdateObject
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from messaging import send_transaction_message


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

async def show_categories(lunch, update: Update):
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


async def show_subcategories(lunch, update: Update):
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


async def apply_category(lunch, update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    
    transaction_id, category_id = query.data.split("_")[1:]
    lunch.update_transaction(transaction_id, TransactionUpdateObject(category_id=category_id))
    updated_transaction = lunch.get_transaction(transaction_id)
    await send_transaction_message(context, updated_transaction, chat_id, query.message.message_id)