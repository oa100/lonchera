import logging
import os
from textwrap import dedent
import traceback
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from handlers.settings import handle_register_token
from telegram.constants import ReactionEmoji

from lunch import NoLunchToken, get_lunch_client_for_chat_id
from handlers.expectations import (
    EXPECTING_TOKEN,
    get_expectation,
    set_expectation,
)
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
    else:
        logger.error(
            f"Update {update} caused error {context.error}",
            exc_info=context.error,
        )


async def handle_generic_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # if waiting for a token, register it
    expectation = get_expectation(get_chat_id(update))
    if expectation and expectation["expectation"] == EXPECTING_TOKEN:
        set_expectation(get_chat_id(update), None)

        await context.bot.delete_message(
            chat_id=get_chat_id(update), message_id=expectation["msg_id"]
        )

        return await handle_register_token(
            update, context, token_override=update.message.text
        )

    logger.info(f"Received unexpected message: {update.message.text}")


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
