import logging
from textwrap import dedent
from lunchable import TransactionUpdateObject
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ReactionEmoji

from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from tx_messaging import get_tx_buttons, send_plaid_details, send_transaction_message

logger = logging.getLogger("tx_handler")


async def handle_btn_skip_transaction(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.edit_message_reply_markup(reply_markup=None)
    await query.answer()


async def handle_btn_cancel_categorization(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    transaction_id = int(query.data.split("_")[1])
    await query.edit_message_reply_markup(reply_markup=get_tx_buttons(transaction_id))
    await query.answer()


async def handle_btn_show_categories(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Updates the message to show the parent categories available"""
    query = update.callback_query
    chat_id = query.message.chat.id
    lunch = get_lunch_client_for_chat_id(chat_id)
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
    await query.answer()


async def handle_btn_show_subcategories(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Updates the transaction with the selected category."""
    query = update.callback_query
    transaction_id, category_id = query.data.split("_")[1:]

    chat_id = query.message.chat.id
    lunch = get_lunch_client_for_chat_id(chat_id)
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
    await query.answer()


async def handle_btn_apply_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Updates the transaction with the selected category."""
    query = update.callback_query
    chat_id = query.message.chat.id

    transaction_id, category_id = query.data.split("_")[1:]
    lunch = get_lunch_client_for_chat_id(chat_id)
    lunch.update_transaction(
        transaction_id, TransactionUpdateObject(category_id=category_id)
    )
    logger.info(f"Changing category for tx {transaction_id} to {category_id}")
    updated_transaction = lunch.get_transaction(transaction_id)
    await send_transaction_message(
        context, updated_transaction, chat_id, query.message.message_id
    )
    await query.answer()


async def handle_btn_dump_plaid_details(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Sends a new message with the plaid metadata of the transaction."""
    query = update.callback_query
    transaction_id = int(query.data.split("_")[1])

    chat_id = query.message.chat.id
    lunch = get_lunch_client_for_chat_id(chat_id)

    transaction = lunch.get_transaction(transaction_id)
    plaid_metadata = transaction.plaid_metadata
    plaid_details = "*Plaid Metadata*\n\n"
    for key, value in plaid_metadata.items():
        if value is not None:
            plaid_details += f"*{key}:* `{value}`\n"

    await query.answer()
    await send_plaid_details(query, context, chat_id, transaction_id, plaid_details)


async def handle_btn_mark_tx_as_reviewed(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Updates the transaction status to reviewed."""
    query = update.callback_query
    chat_id = query.message.chat.id
    lunch = get_lunch_client_for_chat_id(chat_id)
    transaction_id = int(query.data.split("_")[1])
    try:
        lunch.update_transaction(
            transaction_id, TransactionUpdateObject(status="cleared")
        )
        # once the transaction is marked as reviewed, we remove the buttons
        # to make it clear that the transaction was reviewed and no more changes
        # are allowed (except adding notes or tags)
        await query.edit_message_reply_markup(reply_markup=None)
        get_db().mark_as_reviewed(query.message.message_id, chat_id)
        await query.answer()
    except Exception as e:
        await query.answer(
            text=f"Error marking transaction as reviewed: {str(e)}", show_alert=True
        )


async def handle_set_tx_notes_or_tags(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Updates the transaction notes."""
    replying_to_msg_id = update.message.reply_to_message.message_id
    tx_id = get_db().get_tx_associated_with(replying_to_msg_id, update.message.chat_id)

    if tx_id is None:
        logger.error("No transaction ID found in bot data", exc_info=True)
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text=dedent(
                """
                Could not find the transaction associated with the message.
                This is a bug if you have not wiped the db.
                """
            ),
        )
        return

    msg_text = update.message.text
    message_are_tags = True
    for word in msg_text.split(" "):
        if not word.startswith("#"):
            message_are_tags = False
            break

    lunch = get_lunch_client_for_chat_id(update.message.chat_id)
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


async def handle_mark_unreviewed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if update.message.reply_to_message is None:
        await context.bot.send_message(
            chat_id=chat_id,
            text="/mark_unreviewed must be a reply to the tramsaction you want to mark as unreviewed",
        )
        return

    replying_to_msg_id = update.message.reply_to_message.message_id
    transaction_id = get_db().get_tx_associated_with(replying_to_msg_id, chat_id)

    if transaction_id is None:
        await context.bot.send_message(
            chat_id=chat_id,
            text=dedent(
                """
                Could not find the transaction associated with the message.
                This is a bug if you have not wiped the state.
                """
            ),
        )
        return

    logger.info(
        f"Marking transaction {transaction_id} from message {replying_to_msg_id} as unreviewed"
    )
    lunch = get_lunch_client_for_chat_id(chat_id)
    lunch.update_transaction(
        transaction_id, TransactionUpdateObject(status="uncleared")
    )

    # update message to show the right buttons
    updated_tx = lunch.get_transaction(transaction_id)
    await send_transaction_message(
        context, transaction=updated_tx, chat_id=chat_id, message_id=replying_to_msg_id
    )

    # add reaction to the command message
    await context.bot.set_message_reaction(
        chat_id=chat_id,
        message_id=update.message.message_id,
        reaction=ReactionEmoji.OK_HAND_SIGN,
    )
