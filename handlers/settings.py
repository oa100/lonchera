from datetime import timedelta
from textwrap import dedent
from typing import Optional
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.constants import ReactionEmoji

from handlers.expectations import EXPECTING_TOKEN, set_expectation
from lunch import get_lunch_client, get_lunch_client_for_chat_id
from persistence import Settings, get_db
from utils import Keyboard, get_chat_id


async def handle_register_token(
    update: Update, context: ContextTypes.DEFAULT_TYPE, token_override: str = None
):
    # if the message is empty, ask to provide a token
    if token_override is None and len(update.message.text.split(" ")) < 2:
        msg = await context.bot.send_message(
            chat_id=update.message.chat_id,
            text="Please provide a token to register",
        )
        set_expectation(
            get_chat_id(update),
            {
                "expectation": EXPECTING_TOKEN,
                "msg_id": msg.message_id,
            },
        )
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

                (_I deleted the message with the token you provided for security purposes_)
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


def get_current_settings_text(chat_id: int) -> Optional[str]:
    settings = get_db().get_current_settings(chat_id)
    if settings is None:
        return None

    poll_interval = settings.poll_interval_secs
    next_poll_at = ""
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

        last_poll = settings.last_poll_at
        if last_poll:
            next_poll_at = last_poll + timedelta(seconds=settings.poll_interval_secs)
            next_poll_at = (
                f"\n    Next poll at `{next_poll_at.strftime('%a, %b %d at %I:%M %p')}`"
            )
    next_poll_at += "\n    Trigger now: /review\\_transactions"

    return dedent(
        f"""🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂

*Poll interval*: {poll_interval} {next_poll_at}

*Auto\-mark transactions as reviewed*: {"☑️" if settings.auto_mark_reviewed else "☐"}
> When enabled, transactions will be marked as reviewed automatically after being sent to Telegram\.
> When disabled, you need to explicitly mark them as reviewed\.

*API token*: ||{settings.token}||"""
    )


def get_settings_buttons(settings: Settings) -> InlineKeyboardMarkup:
    kbd = Keyboard()
    kbd += ("Change poll interval", "changePollInterval")
    kbd += ("Change token", "registerToken")
    kbd += (
        "Toggle auto-mark reviewed",
        f"toggleAutoMarkReviewed_{settings.auto_mark_reviewed}",
    )
    kbd += ("Trigger Plaid refresh", "triggerPlaidRefresh")
    kbd += ("Log out", "logout")
    kbd += ("Done", "doneSettings")
    return kbd.build()


async def handle_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a message with the current settings."""
    settings_text = get_current_settings_text(update.effective_chat.id)
    if settings_text is None:
        await update.message.reply_text(
            text="No settings found for this chat. Did you register a token?",
        )
        return

    settings = get_db().get_current_settings(update.effective_chat.id)
    await update.message.reply_text(
        text=settings_text,
        reply_markup=get_settings_buttons(settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_btn_set_token_from_button(
    update: Update, _: ContextTypes.DEFAULT_TYPE
):
    msg = await update.callback_query.edit_message_text(
        text="Please provide a token to register",
    )
    set_expectation(
        get_chat_id(update),
        {
            "expectation": EXPECTING_TOKEN,
            "msg_id": msg.message_id,
        },
    )


async def handle_btn_toggle_auto_mark_reviewed(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    settings = get_db().get_current_settings(get_chat_id(update))
    get_db().update_auto_mark_reviewed(
        get_chat_id(update), not settings.auto_mark_reviewed
    )

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text=get_current_settings_text(update.effective_chat.id),
        reply_markup=get_settings_buttons(settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_btn_change_poll_interval(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Changes the poll interval for the chat."""
    if "_" in update.callback_query.data:
        poll_interval = int(update.callback_query.data.split("_")[1])
        get_db().update_poll_interval(get_chat_id(update), poll_interval)
        settings = get_db().get_current_settings(get_chat_id(update))
        await update.callback_query.edit_message_text(
            text=f"_Poll interval updated_\n\n{get_current_settings_text(get_chat_id(update))}",
            reply_markup=get_settings_buttons(settings),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        kbd = Keyboard()
        kbd += ("5 minutes", "changePollInterval_300")
        kbd += ("30 minutes", "changePollInterval_1800")
        kbd += ("1 hour", "changePollInterval_3600")
        kbd += ("4 hours", "changePollInterval_14400")
        kbd += ("24 hours", "changePollInterval_86400")
        kbd += ("Disable", "changePollInterval_0")
        kbd += ("Cancel", "cancelPollIntervalChange")
        await update.callback_query.edit_message_text(
            text="Please choose the new poll interval in minutes...",
            reply_markup=kbd.build(),
        )


async def handle_btn_done_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # delete message
    await context.bot.delete_message(
        chat_id=get_chat_id(update),
        message_id=update.callback_query.message.message_id,
    )


async def handle_logout(update: Update, _: ContextTypes.DEFAULT_TYPE):
    kbd = Keyboard()
    kbd += ("Yes, delete my token", "logout_confirm")
    kbd += ("Nevermind", "logout_cancel")
    await update.callback_query.edit_message_text(
        text=dedent(
            """
            This will remove the API token from the DB and delete all the cache associated with this chat.
            You need to delete the chat history manually.

            Do you want to proceed?
            """
        ),
        reply_markup=kbd.build(),
    )


async def handle_logout_confirm(update: Update, _: ContextTypes.DEFAULT_TYPE):
    get_db().logout(get_chat_id(update))

    await update.callback_query.delete_message()
    await update.callback_query.answer(
        "Your API token has been removed, as well as the transaction history. It was a pleasure to serve you 🖖"
    )


async def handle_logout_cancel(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.delete_message()


async def handle_btn_trigger_plaid_refresh(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    lunch = get_lunch_client_for_chat_id(update.message.chat_id)
    lunch.trigger_fetch_from_plaid()
    await context.bot.set_message_reaction(
        chat_id=update.message.chat_id,
        message_id=update.message.message_id,
        reaction=ReactionEmoji.HANDSHAKE,
    )

    settings_text = get_current_settings_text(get_chat_id(update))
    settings = get_db().get_current_settings(get_chat_id(update))
    await update.callback_query.edit_message_text(
        text=f"_Plaid refresh triggered_\n\n{settings_text}",
        reply_markup=get_settings_buttons(settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
