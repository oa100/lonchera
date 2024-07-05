from datetime import datetime
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

logger = logging.getLogger("budget_handler")


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


async def handle_btn_show_budget_categories(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Updates the message to show the budget categories available."""
    lunch = get_lunch_client_for_chat_id(update.callback_query.message.chat.id)
    budget = get_default_budget(lunch)
    await update.callback_query.answer()
    await show_budget_categories(update, context, budget)


async def handle_btn_hide_budget_categories(
    update: Update, _: ContextTypes.DEFAULT_TYPE
):
    """Updates the message to hide the budget categories."""
    lunch = get_lunch_client_for_chat_id(update.callback_query.message.chat.id)
    budget = get_default_budget(lunch)
    await update.callback_query.answer()
    await hide_budget_categories(update, budget)


async def handle_btn_show_budget_for_category(
    update: Update, _: ContextTypes.DEFAULT_TYPE
):
    """Updates the message to show the budget for a specific category"""
    category_id = int(update.callback_query.data.split("_")[1])
    lunch = get_lunch_client_for_chat_id(update.callback_query.message.chat.id)
    all_budget = get_default_budget(lunch)

    # get super category
    category = lunch.get_category(category_id)
    children_categories_ids = [child.id for child in category.children]

    sub_budget = []
    for budget_item in all_budget:
        if budget_item.category_id in children_categories_ids:
            sub_budget.append(budget_item)

    await update.callback_query.answer()
    await show_bugdget_for_category(update, all_budget, sub_budget)
