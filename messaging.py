from datetime import datetime
import logging
import pytz

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from lunchable.models import TransactionObject, BudgetObject

from typing import List

logger = logging.getLogger('messaging')


def get_buttons(transaction_id: int, plaid=True, skip=True, mark_reviewed=True, categorize=True):
    buttons = []
    if categorize:
        buttons.append(InlineKeyboardButton("Categorize", callback_data=f"categorize_{transaction_id}"))
    if plaid:
        buttons.append(InlineKeyboardButton("Dump plaid details", callback_data=f"plaid_{transaction_id}"))
    if skip:
        buttons.append(InlineKeyboardButton("Skip", callback_data=f"skip_{transaction_id}"))
    if mark_reviewed:
        buttons.append(InlineKeyboardButton("Mark as reviewed", callback_data=f"review_{transaction_id}"))
    # max two buttons per row
    buttons = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return buttons


def get_bugdet_buttons():
    return [
        [
            InlineKeyboardButton("Details", callback_data="showBudgetCategories"),
        ]
    ]


def get_budget_category_buttons(budget_items: List[BudgetObject]):
    buttons = []
    for budget_item in budget_items:
        buttons.append(InlineKeyboardButton(budget_item.category_name, callback_data=f"showBudgetDetails_{budget_item.category_id}"))

    # 3 buttons per row
    buttons = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]

    # add exit button
    buttons.append([InlineKeyboardButton("Exit", callback_data="exitBudgetDetails")])
    return buttons


async def send_transaction_message(context: ContextTypes.DEFAULT_TYPE, transaction: TransactionObject, chat_id, message_id=None) -> None:
    # Format the amount with monospaced font
    formatted_amount = f"`${transaction.amount:.2f}`"

    # Get the datetime from plaid_metadata
    authorized_datetime = transaction.plaid_metadata.get('authorized_datetime')
    if authorized_datetime:
        date_time = datetime.fromisoformat(authorized_datetime.replace('Z', '-02:00'))
        pst_tz = pytz.timezone('US/Pacific')
        pst_date_time = date_time.astimezone(pst_tz)
        formatted_date_time = pst_date_time.strftime("%a, %b %d at %I:%M %p PST")
    else:
        formatted_date_time = transaction.plaid_metadata.get('date')

    # Get category and category group
    category = transaction.category_name or "Uncategorized"
    category_group = transaction.category_group_name or "No Group"

    # Get account display name
    account_name = transaction.plaid_account_display_name or "N/A"

    # split the category group into two: the first emoji and the rest of the string
    emoji, rest = category_group.split(" ", 1)
    rest = rest.title().replace(" ", "")

    message = f"{emoji} #*{rest}*\n\n"
    message += f"*Payee:* {transaction.payee}\n"
    message += f"*Amount:* {formatted_amount}\n"
    message += f"*Date/Time:* {formatted_date_time}\n"
    message += f"*Category:* #{category.title().replace(" ", "")} \n"
    message += f"*Account:* #{account_name.title().replace(" ", "")}\n"
    if transaction.notes:
        message += f"*Notes:* {transaction.notes}\n"
    if transaction.is_pending:
        message += f"\n_This is a pending transaction_\n"


    if transaction.is_pending:
        # when a transaction is pending, we don't want to mark it as reviewed
        keyboard = get_buttons(transaction.id, mark_reviewed=False, skip=False)
    else:
        keyboard = get_buttons(transaction.id)

    reply_markup = InlineKeyboardMarkup(keyboard)

    if message_id:
        # edit existing message
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    else:
        # send a new message
        logger.info(f"Sending message to chat_id {chat_id}: {message}")
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        context.bot_data[msg.id] = transaction.id
        logger.info(f"Current bot data: {context.bot_data}")



def build_budget_message(budget: List[BudgetObject]):
    msg = ""
    total_budget = 0
    total_spent = 0
    budget_date = next(iter(budget[0].data.keys()))
    for budget_item in budget:
        if budget_item.category_group_name is None and budget_item.category_id is not None:
            _, budget_data = next(iter(budget_item.data.items()))
            spent_already = budget_data.spending_to_base
            budgeted = budget_data.budget_to_base
            total_budget += budgeted
            total_spent += spent_already
            pct = spent_already*100/budgeted

            # number of blocks to draw (max 10)
            blocks = int(pct/10)
            empty = 10 - blocks
            bar = "█"*blocks + "░"*empty
            extra = ""
            if blocks > 10:
                bar = "█"*10
                extra = "▓"*(blocks-10)

            # split the category group into two: the first emoji and the rest of the string
            emoji, cat_name = budget_item.category_name.split(" ", 1)
            cat_name = cat_name.title().replace(" ", "")

            msg += f"{emoji} `[{bar}]{extra}`\n"
            msg += f"#*{cat_name}* - `{spent_already:.1f}` of `{budgeted:.1f}` USD ({pct:.1f}%)\n\n"

    msg = f"*Budget for {budget_date.strftime('%B %Y')}*\n\n{msg}"
    return f"{msg}\n\nTotal spent: `{total_spent:.1f}` of `{total_budget:.1f}` USD ({total_spent*100/total_budget:.1f}%)"



async def send_budget(update: Update, context: ContextTypes.DEFAULT_TYPE, budget: List[BudgetObject]) -> None:
    msg = build_budget_message(budget)

    if msg != "":
        chat_id = update.message.chat.id
        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(get_bugdet_buttons()),
        )
    else:
        # TODO: handle this case
        pass


async def show_budget_categories(update: Update, _: ContextTypes.DEFAULT_TYPE, budget: List[BudgetObject]) -> None:
    categories = []
    for budget_item in budget:
        if budget_item.category_group_name is None and budget_item.category_id is not None:
            categories.append(budget_item)

    query = update.callback_query
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(get_budget_category_buttons(categories)))



async def hide_budget_categories(update: Update, budget: List[BudgetObject]) -> None:
    msg = build_budget_message(budget)
    query = update.callback_query
    await query.edit_message_text(
        text=msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(get_bugdet_buttons()),
    )



async def show_bugdget_for_category(update: Update, all_budget: List[BudgetObject], category_budget: List[BudgetObject]) -> None:
    msg = ""
    total_budget = 0
    total_spent = 0

    category_group_name = ""
    budget_date = next(iter(category_budget[0].data.keys()))

    for budget_item in category_budget:
        spent_already = budget_item.data[budget_date].spending_to_base
        budgeted = budget_item.data[budget_date].budget_to_base
        if budgeted == 0 or budgeted is None:
            continue

        category_group_name = budget_item.category_group_name

        total_budget += budgeted
        total_spent += spent_already
        pct = spent_already*100/budgeted

        # number of blocks to draw (max 10)
        blocks = int(pct/10)
        empty = 10 - blocks
        bar = "█"*blocks + "░"*empty
        extra = ""
        if blocks > 10:
            bar = "█"*10
            extra = "▓"*(blocks-10)

        msg += f"`[{bar}]{extra}`\n"
        msg += f"*{budget_item.category_name}* - `{spent_already:.1f}` of `{budgeted:.1f}` USD (`{pct:.1f}`%)\n\n"

    if total_budget > 0:
        msg = f"*{category_group_name} budget for {budget_date.strftime('%B %Y')}*\n\n{msg}"
        msg += f"Total spent: `{total_spent:.1f}` of `{total_budget:.1f}` USD ({total_spent*100/total_budget:.1f}%)"
    else:
        msg = "This category seems to have a global budget, not a per subcategory one"

    categories = []
    for budget_item in all_budget:
        if budget_item.category_group_name is None and budget_item.category_id is not None:
            categories.append(budget_item)
    await update.callback_query.edit_message_text(
        text=msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(get_budget_category_buttons(categories)),
    )



async def send_plaid_details(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, chat_id: int, transaction_id: str, plaid_details: str):
    await context.bot.send_message(
        chat_id=chat_id,
        text=plaid_details,
        parse_mode=ParseMode.MARKDOWN,
        reply_to_message_id=query.message.message_id,
    )

    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(get_buttons(transaction_id, plaid=False)))