from datetime import datetime
import logging
import os
from textwrap import dedent
import traceback
from typing import Optional
from lunchable import LunchMoney, TransactionUpdateObject
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ReactionEmoji, ParseMode
from persistence import get_db

from budget_messaging import (
    hide_budget_categories,
    send_budget,
    show_budget_categories,
    show_bugdget_for_category,
)
from lunch import NoLunchToken, get_lunch_client, get_lunch_client_for_chat_id
from tx_messaging import send_plaid_details, send_transaction_message
from utils import get_chat_id

logger = logging.getLogger("handlers")


async def handle_start(update: Update):
    await update.message.reply_text(
        text=dedent(
            """
            Welcome to Lonchera! A Telegram bot that helps you stay on top of your Lunch Money transactions.
            To start, please register your [Lunch Money API token](https://my.lunchmoney.app/developers) by sending:
            
            `/register <token>`

            Only one token is supported per chat.
            """
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True,
    )


EXPECTING_TOKEN = "token"
current_expectation = {}


async def handle_register_token(
    update: Update, context: ContextTypes.DEFAULT_TYPE, token_override: str = None
):
    # if the message is empty, ask to provide a token
    if token_override is None and len(update.message.text.split(" ")) < 2:
        msg = await context.bot.send_message(
            chat_id=update.message.chat_id,
            text="Please provide a token to register",
        )
        current_expectation[get_chat_id(update)] = {
            "expectation": EXPECTING_TOKEN,
            "msg_id": msg.message_id,
        }
        return

    if token_override is not None:
        token = token_override
    else:
        token = update.message.text.split(" ")[1]

    # delete the message with the token
    await context.bot.delete_message(
        chat_id=update.message.chat_id, message_id=update.message.message_id
    )

    try:
        # make sure the token is valid
        lunch = get_lunch_client(token)
        lunch_user = lunch.get_user()
        get_db().save_token(update.message.chat_id, token)

        # TODO include basic docs of the available commands
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text=dedent(
                f"""
                Hello {lunch_user.user_name}!

                Your token was successfully registered. Will start polling for unreviewed transactions.

                Use /settings to change my behavior.

                (_I deleted token you provided for security purposes_)
                """
            ),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text=dedent(
                f"""
                Failed to register token `{token}`:
                ```
                {e}
                ```
                """
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def handle_show_categories(update: Update):
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


async def handle_show_subcategories(update: Update):
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


async def handle_apply_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def handle_dump_plaid_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a new message with the plaid metadata of the transaction."""
    query = update.callback_query
    transaction_id = int(query.data.split("_")[1])

    chat_id = query.message.chat.id
    lunch = get_lunch_client_for_chat_id(chat_id)

    transaction = lunch.get_transaction(transaction_id)
    plaid_metadata = transaction.plaid_metadata
    plaid_details = f"*Plaid Metadata*\n\n"
    for key, value in plaid_metadata.items():
        if value is not None:
            plaid_details += f"*{key}:* `{value}`\n"

    await send_plaid_details(query, context, chat_id, transaction_id, plaid_details)


async def handle_mark_tx_as_reviewed(update: Update):
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
    except Exception as e:
        await query.edit_message_text(text=f"Error updating transaction: {str(e)}")


async def handle_set_tx_notes_or_tags(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Updates the transaction notes."""
    replying_to_msg_id = update.message.reply_to_message.message_id
    tx_id = get_db().get_tx_associated_with(replying_to_msg_id, update.message.chat_id)

    if tx_id is None:
        logger.error("No transaction ID found in bot data", exc_info=True)
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


def get_default_budget(lunch: LunchMoney):
    """Get the budget for the current month."""
    # get a datetime of the first day of the current month
    first_day_current_month = datetime.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    # get a datetime of the current day
    current_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    return lunch.get_budgets(start_date=first_day_current_month, end_date=current_day)


async def handle_show_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a message with the current budget."""
    lunch = get_lunch_client_for_chat_id(update.message.chat_id)
    logger.info("Pulling budget...")
    budget = get_default_budget(lunch)
    await send_budget(update, context, budget)


async def handle_show_budget_categories(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Updates the message to show the budget categories available."""
    lunch = get_lunch_client_for_chat_id(update.callback_query.message.chat.id)
    budget = get_default_budget(lunch)
    await show_budget_categories(update, context, budget)


async def handle_hide_budget_categories(update: Update):
    """Updates the message to hide the budget categories."""
    lunch = get_lunch_client_for_chat_id(update.callback_query.message.chat.id)
    budget = get_default_budget(lunch)
    await hide_budget_categories(update, budget)


async def handle_show_budget_for_category(update: Update, category_id: int):
    """Updates the message to show the budget for a specific category"""
    lunch = get_lunch_client_for_chat_id(update.callback_query.message.chat.id)
    all_budget = get_default_budget(lunch)

    # get super category
    category = lunch.get_category(category_id)
    children_categories_ids = [child.id for child in category.children]

    sub_budget = []
    for budget_item in all_budget:
        if budget_item.category_id in children_categories_ids:
            sub_budget.append(budget_item)

    await show_bugdget_for_category(update, all_budget, sub_budget)


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
            text="Could not find the transaction associated with the message. This is a bug if you have not wiped the state.",
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


# TODO: detect when no token is present, and send a message to the user to register a token
async def handle_errors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log Errors caused by Updates."""
    if isinstance(context.error, NoLunchToken):
        await context.bot.send_message(
            chat_id=get_chat_id(update),
            text=dedent(
                """
                No token registered for this chat. Please register a token using:
                `/register <token>`
                """
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    if os.environ.get("DEBUG"):
        error = context.error
        await context.bot.send_message(
            chat_id=get_chat_id(update),
            text=dedent(
                f"""
                An error occurred:
                ```
                {''.join(traceback.format_exception(type(error), error, error.__traceback__))}
                ```
                """
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        logger.error(
            f"Update {update} caused error {context.error}",
            exc_info=context.error,
        )


async def handle_generic_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # if waiting for a token, register it
    expectation = current_expectation.get(get_chat_id(update), None)
    if expectation["expectation"] == EXPECTING_TOKEN:
        current_expectation[get_chat_id(update)] = None

        await context.bot.delete_message(
            chat_id=get_chat_id(update), message_id=expectation["msg_id"]
        )

        return await handle_register_token(
            update, context, token_override=update.message.text
        )

    logger.info(f"Received unexpected message: {update.message.text}")


def get_current_settings_text(chat_id: int) -> Optional[str]:
    settings = get_db().get_current_settings(chat_id)
    if settings is None:
        return None

    poll_interval = settings["poll_interval_secs"]
    if poll_interval is None or poll_interval == 0:
        poll_interval = "Disabled"
    else:
        if poll_interval < 3600:
            poll_interval = f"`{poll_interval // 60} minutes`"
        elif poll_interval < 86400:
            if poll_interval // 3600 == 1:
                poll_interval = "`1 hour`"
            else:
                poll_interval = f"`{poll_interval // 3600} hours`"
        else:
            if poll_interval // 86400 == 1:
                poll_interval = "`1 day`"
            else:
                poll_interval = f"`{poll_interval // 86400} days`"

    token = settings["token"]

    return dedent(
        f"""
        *Current settings*

        Poll interval: {poll_interval}
        API token: ||{token}||
        """
    )


def get_settings_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Change poll interval",
                    callback_data=f"changePollInterval",
                ),
                InlineKeyboardButton(
                    "Change token",
                    callback_data=f"registerToken",
                ),
            ],
            [
                InlineKeyboardButton(
                    "Done",
                    callback_data="doneSettings",
                )
            ],
        ]
    )


async def handle_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a message with the current settings."""
    settings_text = get_current_settings_text(update.message.chat_id)
    if settings_text is None:
        await update.message.reply_text(
            text="No settings found for this chat. Did you register a token?",
        )
        return

    await update.message.reply_text(
        text=settings_text,
        reply_markup=get_settings_buttons(),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_set_token_from_button(update: Update, _: ContextTypes.DEFAULT_TYPE):
    msg = await update.callback_query.edit_message_text(
        text="Please provide a token to register",
    )
    current_expectation[get_chat_id(update)] = {
        "expectation": EXPECTING_TOKEN,
        "msg_id": msg.message_id,
    }


async def handle_change_poll_interval(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Changes the poll interval for the chat."""
    if "_" in update.callback_query.data:
        poll_interval = int(update.callback_query.data.split("_")[1])
        get_db().update_poll_interval(get_chat_id(update), poll_interval)
        await update.callback_query.edit_message_text(
            text=f"_Poll interval updated_\n\n{get_current_settings_text(get_chat_id(update))}",
            reply_markup=get_settings_buttons(),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        await update.callback_query.edit_message_text(
            text="Please choose the new poll interval in minutes...",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "5 minutes",
                            callback_data=f"changePollInterval_300",
                        ),
                        InlineKeyboardButton(
                            "30 minutes",
                            callback_data=f"changePollInterval_1800",
                        ),
                        InlineKeyboardButton(
                            "1 hour",
                            callback_data=f"changePollInterval_3600",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "4 hours",
                            callback_data=f"changePollInterval_14400",
                        ),
                        InlineKeyboardButton(
                            "24 hours",
                            callback_data=f"changePollInterval_86400",
                        ),
                        InlineKeyboardButton(
                            "Disable",
                            callback_data=f"changePollInterval_0",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "Cancel",
                            callback_data="cancelPollIntervalChange",
                        )
                    ],
                ]
            ),
        )
