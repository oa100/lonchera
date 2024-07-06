import logging
import os
from textwrap import dedent
import traceback
from lunchable import TransactionUpdateObject
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from handlers.settings import handle_register_token
from telegram.constants import ReactionEmoji

from lunch import NoLunchToken, get_lunch_client_for_chat_id
from handlers.expectations import (
    EDIT_NOTES,
    EXPECTING_TOKEN,
    RENAME_PAYEE,
    SET_TAGS,
    clear_expectation,
    get_expectation,
)
from tx_messaging import send_transaction_message
from utils import get_chat_id

logger = logging.getLogger("handlers")


async def handle_start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        text=dedent(
            """
            Welcome to Lonchera! A Telegram bot that helps you stay on top of your Lunch Money transactions.
            To start, please register your [Lunch Money API token](https://my.lunchmoney.app/developers) by sending:

            `/register <token>`

            Only one token is supported per chat.
            """
        ),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def handle_errors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log Errors caused by Updates."""
    if update is None:
        logger.error("Update is None", exc_info=context.error)
        return
    if isinstance(context.error, NoLunchToken):
        await context.bot.send_message(
            chat_id=get_chat_id(update),
            text=dedent(
                """
                No token registered for this chat. Please register a token using:
                `/register <token>`
                """
            ),
            parse_mode=ParseMode.MARKDOWN,
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
            parse_mode=ParseMode.MARKDOWN,
        )
    logger.error(
        f"Update {update} caused error {context.error}",
        exc_info=context.error,
    )


async def handle_generic_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    # if waiting for a token, register it
    expectation = get_expectation(get_chat_id(update))
    if expectation and expectation["expectation"] == EXPECTING_TOKEN:
        clear_expectation(get_chat_id(update))

        await context.bot.delete_message(
            chat_id=get_chat_id(update), message_id=expectation["msg_id"]
        )

        await handle_register_token(update, context, token_override=update.message.text)
        return True
    elif expectation and expectation["expectation"] == RENAME_PAYEE:
        clear_expectation(get_chat_id(update))

        # updates the transaction with the new payee
        lunch = get_lunch_client_for_chat_id(get_chat_id(update))
        transaction_id = int(expectation["transaction_id"])
        lunch.update_transaction(
            transaction_id, TransactionUpdateObject(payee=update.message.text)
        )

        # edit the message to reflect the new payee
        updated_transaction = lunch.get_transaction(transaction_id)
        msg_id = int(expectation["msg_id"])
        await send_transaction_message(
            context=context,
            transaction=updated_transaction,
            chat_id=get_chat_id(update),
            message_id=msg_id,
        )

        # react to the message
        await context.bot.set_message_reaction(
            chat_id=update.message.chat_id,
            message_id=update.message.message_id,
            reaction=ReactionEmoji.WRITING_HAND,
        )
        return True
    elif expectation and expectation["expectation"] == EDIT_NOTES:
        clear_expectation(get_chat_id(update))

        # updates the transaction with the new notes
        lunch = get_lunch_client_for_chat_id(get_chat_id(update))
        transaction_id = int(expectation["transaction_id"])
        lunch.update_transaction(
            transaction_id, TransactionUpdateObject(notes=update.message.text)
        )

        # edit the message to reflect the new notes
        updated_transaction = lunch.get_transaction(transaction_id)
        msg_id = int(expectation["msg_id"])
        await send_transaction_message(
            context=context,
            transaction=updated_transaction,
            chat_id=get_chat_id(update),
            message_id=msg_id,
        )

        # react to the message
        await context.bot.set_message_reaction(
            chat_id=update.message.chat_id,
            message_id=update.message.message_id,
            reaction=ReactionEmoji.WRITING_HAND,
        )
        return True
    elif expectation and expectation["expectation"] == SET_TAGS:
        # make sure they look like tags
        message_are_tags = True
        for word in update.message.text.split(" "):
            if not word.startswith("#"):
                message_are_tags = False
                break

        if not message_are_tags:
            await context.bot.send_message(
                chat_id=get_chat_id(update),
                text=dedent(
                    """
                    The message should only contain words suffixed with a hashtag `#`.
                    For example: `#tag1 #tag2 #tag3`
                    """
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
            return True

        clear_expectation(get_chat_id(update))

        # updates the transaction with the new notes
        lunch = get_lunch_client_for_chat_id(get_chat_id(update))
        transaction_id = int(expectation["transaction_id"])

        tags_without_hashtag = [
            tag[1:] for tag in update.message.text.split(" ") if tag.startswith("#")
        ]
        logger.info(
            f"Setting tags to transaction ({transaction_id}): {tags_without_hashtag}"
        )
        lunch.update_transaction(
            transaction_id, TransactionUpdateObject(tags=tags_without_hashtag)
        )

        # edit the message to reflect the new notes
        updated_transaction = lunch.get_transaction(transaction_id)
        msg_id = int(expectation["msg_id"])
        await send_transaction_message(
            context=context,
            transaction=updated_transaction,
            chat_id=get_chat_id(update),
            message_id=msg_id,
        )

        # react to the message
        await context.bot.set_message_reaction(
            chat_id=update.message.chat_id,
            message_id=update.message.message_id,
            reaction=ReactionEmoji.WRITING_HAND,
        )
        return True

    return False


async def handle_trigger_plaid_refresh(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    lunch = get_lunch_client_for_chat_id(update.message.chat_id)
    lunch.trigger_fetch_from_plaid()
    await context.bot.set_message_reaction(
        chat_id=update.message.chat_id,
        message_id=update.message.message_id,
        reaction=ReactionEmoji.HANDSHAKE,
    )
