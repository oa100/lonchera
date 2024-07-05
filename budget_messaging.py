from datetime import datetime
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from lunchable.models import BudgetObject

from typing import List, Optional

from utils import get_chat_id, make_tag

logger = logging.getLogger("messaging")


def get_bugdet_buttons(current_budget_date: datetime) -> InlineKeyboardMarkup:
    if current_budget_date.month == 1:
        previous_month = current_budget_date.replace(
            month=12, year=current_budget_date.year - 1
        )
    else:
        previous_month = current_budget_date.replace(
            month=current_budget_date.month - 1
        )

    first_day_current_month = datetime.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    next_month = None
    if current_budget_date < first_day_current_month:
        if current_budget_date.month == 12:
            next_month = current_budget_date.replace(
                month=1, year=current_budget_date.year + 1
            )
        else:
            next_month = current_budget_date.replace(
                month=current_budget_date.month + 1
            )

    buttons = []
    buttons.append(
        InlineKeyboardButton(
            f"⏮️ {previous_month.strftime('%B %Y')}",
            callback_data=f"showBudget_{previous_month.isoformat()}",
        )
    )
    if next_month:
        buttons.append(
            InlineKeyboardButton(
                f"{next_month.strftime('%B %Y')} ⏭️",
                callback_data=f"showBudget_{next_month.isoformat()}",
            )
        )

    return InlineKeyboardMarkup(
        [
            buttons,
            [
                InlineKeyboardButton(
                    "Details",
                    callback_data=f"showBudgetCategories_{current_budget_date.isoformat()}",
                )
            ],
        ],
    )


def get_budget_category_buttons(
    budget_items: List[BudgetObject], budget_date: datetime
) -> InlineKeyboardMarkup:
    buttons = []
    for budget_item in budget_items:
        buttons.append(
            InlineKeyboardButton(
                budget_item.category_name,
                callback_data=f"showBudgetDetails_{budget_date.isoformat()}_{budget_item.category_id}",
            )
        )

    # 3 buttons per row
    buttons = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]

    # add exit button
    buttons.append(
        [InlineKeyboardButton("Exit", callback_data=f"exitBudgetDetails_{budget_date}")]
    )
    return InlineKeyboardMarkup(buttons)


def build_budget_message(budget: List[BudgetObject], budget_date: datetime):
    msg = ""
    total_budget = 0
    total_spent = 0
    for budget_item in budget:
        if (
            budget_item.category_group_name is None
            and budget_item.category_id is not None
        ):
            _, budget_data = next(iter(budget_item.data.items()))
            spent_already = budget_data.spending_to_base
            budgeted = budget_data.budget_to_base
            if budgeted is None:
                return f"No budget data available for the month of {budget_date.strftime('%B %Y')}"
            total_budget += budgeted
            total_spent += spent_already
            pct = spent_already * 100 / budgeted

            # number of blocks to draw (max 10)
            blocks = int(pct / 10)
            empty = 10 - blocks
            bar = "█" * blocks + "░" * empty
            extra = ""
            if blocks > 10:
                bar = "█" * 10
                extra = "▓" * (blocks - 10)

            # split the category group into two: the first emoji and the rest of the string
            emoji, cat_name = budget_item.category_name.split(" ", 1)
            cat_name = make_tag(cat_name)

            msg += f"{emoji} `[{bar}]{extra}`\n"
            msg += f"{cat_name} - `{spent_already:.1f}` of `{budgeted:.1f}`"
            msg += f" {budget_data.budget_currency} (`{pct:.1f}%`)\n\n"

    msg = f"*Budget for {budget_date.strftime('%B %Y')}*\n\n{msg}"
    msg += f"\n\nTotal spent: `{total_spent:.1f}` of `{total_budget:.1f}`"
    msg += f" {budget_data.budget_currency} (`{total_spent*100/total_budget:.1f}%`)"
    return msg


async def send_budget(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    budget: List[BudgetObject],
    first_day_of_budget: datetime,
    message_id: Optional[int],
) -> None:
    msg = build_budget_message(budget, first_day_of_budget)

    if message_id:
        await context.bot.edit_message_text(
            chat_id=get_chat_id(update),
            message_id=message_id,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_bugdet_buttons(first_day_of_budget),
        )
    else:
        await context.bot.send_message(
            chat_id=get_chat_id(update),
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_bugdet_buttons(first_day_of_budget),
        )


async def show_budget_categories(
    update: Update,
    _: ContextTypes.DEFAULT_TYPE,
    budget: List[BudgetObject],
    budget_date: datetime,
) -> None:
    categories = []
    for budget_item in budget:
        if (
            budget_item.category_group_name is None
            and budget_item.category_id is not None
        ):
            categories.append(budget_item)

    query = update.callback_query
    await query.edit_message_reply_markup(
        reply_markup=get_budget_category_buttons(categories, budget_date)
    )


async def hide_budget_categories(
    update: Update, budget: List[BudgetObject], budget_date: datetime
) -> None:
    msg = build_budget_message(budget, budget_date)
    query = update.callback_query
    await query.edit_message_text(
        text=msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_bugdet_buttons(budget_date),
    )


async def show_bugdget_for_category(
    update: Update,
    all_budget: List[BudgetObject],
    category_budget: List[BudgetObject],
    budget_date: datetime,
) -> None:
    msg = ""
    total_budget = 0
    total_spent = 0

    category_group_name = ""

    # convert datetime to date
    budget_date_key = datetime.date(budget_date)

    for budget_item in category_budget:
        budget_data = budget_item.data[budget_date_key]
        spent_already = budget_data.spending_to_base
        budgeted = budget_data.budget_to_base
        if budgeted == 0 or budgeted is None:
            continue

        category_group_name = budget_item.category_group_name

        total_budget += budgeted
        total_spent += spent_already
        pct = spent_already * 100 / budgeted

        # number of blocks to draw (max 10)
        blocks = int(pct / 10)
        empty = 10 - blocks
        bar = "█" * blocks + "░" * empty
        extra = ""
        if blocks > 10:
            bar = "█" * 10
            extra = "▓" * (blocks - 10)

        msg += f"`[{bar}]{extra}`\n"
        msg += (
            f"*{budget_item.category_name}* - `{spent_already:.1f}` of `{budgeted:.1f}`"
        )
        msg += f" {budget_data.budget_currency} (`{pct:.1f}%`)\n"

        # show transactions list
        if budget_data.num_transactions > 0:
            plural = ""
            if budget_data.num_transactions > 1:
                plural = "s"
            msg += f"    _{budget_data.num_transactions} transaction{plural}_\n\n"
        else:
            msg += "\n"

    if total_budget > 0:
        msg = f"*{category_group_name} budget for {budget_date.strftime('%B %Y')}*\n\n{msg}"
        msg += f"Total spent: `{total_spent:.1f}` of `{total_budget:.1f}`"
        msg += f" {budget_data.budget_currency} (`{total_spent*100/total_budget:.1f}%`)"
    else:
        msg = "This category seems to have a global budget, not a per subcategory one"

    categories = []
    for budget_item in all_budget:
        if (
            budget_item.category_group_name is None
            and budget_item.category_id is not None
        ):
            categories.append(budget_item)

    await update.callback_query.edit_message_text(
        text=msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_budget_category_buttons(categories, budget_date),
    )
