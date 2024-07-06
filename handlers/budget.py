from datetime import datetime, timedelta
import logging
from lunchable import LunchMoney
from telegram import Update
from telegram.ext import ContextTypes

from budget_messaging import (
    hide_budget_categories,
    send_budget,
    show_budget_categories,
    show_bugdget_for_category,
)
from lunch import get_lunch_client_for_chat_id
from utils import get_chat_id

logger = logging.getLogger("budget_handler")


def end_of_month_for(d: datetime) -> datetime:
    # Determine the first day of the next month
    if d.month == 12:  # December
        d = datetime(d.year + 1, 1, 1)
    else:
        d = datetime(d.year, d.month + 1, 1)
    # Subtract one day from the first day of the next month
    return d - timedelta(days=1)


def get_default_budget_range() -> tuple[datetime, datetime]:
    """Get the budget for the current month."""
    # get a datetime of the first day of the current month
    first_day_current_month = datetime.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    # get the end of the month
    end_of_month = end_of_month_for(first_day_current_month)

    return first_day_current_month, end_of_month


def get_budget_range_from(date: datetime) -> tuple[datetime, datetime]:
    end_of_month = end_of_month_for(date)
    return date, end_of_month


def get_default_budget(lunch: LunchMoney):
    """Get the budget for the current month."""
    # get a datetime of the first day of the current month
    first_day_current_month, final_day_current_month = get_default_budget_range()

    return lunch.get_budgets(
        start_date=first_day_current_month, end_date=final_day_current_month
    )


async def handle_show_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a message with the current budget."""
    message_id = None
    if update.callback_query:
        budget_date = update.callback_query.data.split("_")[1]
        budget_date, budget_end_date = get_budget_range_from(
            datetime.fromisoformat(budget_date)
        )
        message_id = update.callback_query.message.message_id
    else:
        budget_date, budget_end_date = get_default_budget_range()

    lunch = get_lunch_client_for_chat_id(get_chat_id(update))
    logger.info("Pulling budget...")

    budget = lunch.get_budgets(start_date=budget_date, end_date=budget_end_date)
    await send_budget(update, context, budget, budget_date, message_id)


async def handle_btn_show_budget_categories(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Updates the message to show the budget categories available."""
    budget_date = update.callback_query.data.split("_")[1]
    budget_date = datetime.fromisoformat(budget_date)

    lunch = get_lunch_client_for_chat_id(update.callback_query.message.chat.id)

    budget_date, final_day_current_month = get_budget_range_from(budget_date)
    budget = lunch.get_budgets(start_date=budget_date, end_date=final_day_current_month)

    await update.callback_query.answer()
    await show_budget_categories(update, context, budget, budget_date)


async def handle_btn_hide_budget_categories(
    update: Update, _: ContextTypes.DEFAULT_TYPE
):
    """Updates the message to hide the budget categories."""
    budget_date = update.callback_query.data.split("_")[1]
    budget_date = datetime.fromisoformat(budget_date)

    lunch = get_lunch_client_for_chat_id(update.callback_query.message.chat.id)

    budget_date, budget_end_date = get_budget_range_from(budget_date)
    budget = lunch.get_budgets(start_date=budget_date, end_date=budget_end_date)

    await update.callback_query.answer()
    await hide_budget_categories(update, budget, budget_date)


async def handle_btn_show_budget_for_category(
    update: Update, _: ContextTypes.DEFAULT_TYPE
):
    """Updates the message to show the budget for a specific category"""
    parts = update.callback_query.data.split("_")
    budget_date = parts[1]
    budget_date = datetime.fromisoformat(budget_date)
    category_id = int(parts[2])

    lunch = get_lunch_client_for_chat_id(update.callback_query.message.chat.id)

    budget_date, budget_end_date = get_budget_range_from(budget_date)
    all_budget = lunch.get_budgets(start_date=budget_date, end_date=budget_end_date)

    # get super category
    category = lunch.get_category(category_id)
    children_categories_ids = [child.id for child in category.children]

    sub_budget = []
    for budget_item in all_budget:
        if budget_item.category_id in children_categories_ids:
            sub_budget.append(budget_item)

    await update.callback_query.answer()
    await show_bugdget_for_category(update, all_budget, sub_budget, budget_date)