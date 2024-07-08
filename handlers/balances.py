from textwrap import dedent
from typing import List, Optional
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from lunch import get_lunch_client_for_chat_id
from lunchable.models import PlaidAccountObject, AssetsObject, CryptoObject
from utils import (
    Keyboard,
    get_chat_id,
    get_crypto_symbol,
    get_emoji_for_account_type,
    make_tag,
)

# Constants for button states
SHOW_DETAILS = 1 << 0
SHOW_BALANCES = 1 << 1
SHOW_ASSETS = 1 << 2
SHOW_CRYPTO = 1 << 3


# Helper functions to check the state of each field given a mask
def is_show_details(mask: int) -> bool:
    return bool(mask & SHOW_DETAILS)


def is_show_balances(mask: int) -> bool:
    return bool(mask & SHOW_BALANCES)


def is_show_assets(mask: int) -> bool:
    return bool(mask & SHOW_ASSETS)


def is_show_crypto(mask: int) -> bool:
    return bool(mask & SHOW_CRYPTO)


def get_accounts_buttons(current_mask: int) -> InlineKeyboardMarkup:
    kbd = Keyboard()

    def emoji_for_field(field: int) -> str:
        return "☑️" if bool(current_mask & field) else "☐"

    # Toggle the state of each button's corresponding bit in the mask
    show_balances_mask = current_mask ^ SHOW_BALANCES
    kbd += (
        f"{emoji_for_field(SHOW_BALANCES)} Show balances",
        f"accountsBalances_{show_balances_mask}",
    )

    show_assets_mask = current_mask ^ SHOW_ASSETS
    kbd += (
        f"{emoji_for_field(SHOW_ASSETS)} Show assets",
        f"accountsBalances_{show_assets_mask}",
    )

    show_crypto_mask = current_mask ^ SHOW_CRYPTO
    kbd += (
        f"{emoji_for_field(SHOW_CRYPTO)} Show crypto",
        f"accountsBalances_{show_crypto_mask}",
    )

    show_details_mask = current_mask ^ SHOW_DETAILS
    kbd += (
        f"{emoji_for_field(SHOW_DETAILS)}  Show details",
        f"accountsBalances_{show_details_mask}",
    )

    return kbd.build()


def get_accounts_summary_text(
    accts: List[PlaidAccountObject], show_details: bool
) -> str:
    """Returns a message with the accounts and their balances."""
    by_group = {}
    for acct in accts:
        by_group.setdefault(acct.type, []).append(acct)

    txt = ""
    for acct_type, accts in by_group.items():
        txt += f"{get_emoji_for_account_type(acct_type)} {make_tag(acct_type, title=True)}\n\n"
        for acct in accts:
            if show_details:
                institution = ""
                if acct.institution_name and acct.institution_name != (
                    acct.display_name or acct.name
                ):
                    institution = f" (_{acct.institution_name}_)"
                txt += f"*{acct.display_name or acct.name}* {institution}\n"
                txt += f"Balance: `${acct.balance:,.2f}` {acct.currency.upper()}"
                if acct.limit:
                    txt += f" / `${acct.limit:,.2f}` {acct.currency.upper()}\n"
                else:
                    txt += "\n"
                txt += f"Last update: {acct.balance_last_update.strftime('%a, %b %d at %I:%M %p')}\n"
                txt += f"Status: {acct.status}\n\n"
            else:
                txt += f" • *{acct.display_name or acct.name}*: `${acct.balance:,.2f}` {acct.currency.upper()}\n"
        txt += "\n"

    return dedent(
        f"""*BALANCES*

{txt}
    """
    )


def get_assets_summary_text(assets: List[AssetsObject], show_details: bool) -> str:
    """Returns a message with the assets and their balances."""
    by_group = {}
    for asset in assets:
        by_group.setdefault(asset.type_name, []).append(asset)

    txt = ""
    for type, assets in by_group.items():
        txt += f"{get_emoji_for_account_type(type)} {make_tag(type, title=True)}\n\n"
        for asset in assets:
            if show_details:
                institution = ""
                if asset.institution_name and asset.institution_name != (
                    asset.display_name or asset.name
                ):
                    institution = f" (_{asset.institution_name}_)"
                txt += f"*{asset.display_name or asset.name}* {institution}\n"
                txt += f"Balance: `${asset.balance:,.2f}` {asset.currency.upper()}\n"
                txt += f"Last update: {asset.balance_as_of.strftime('%a, %b %d at %I:%M %p')}\n"
            else:
                txt += f" • *{asset.display_name or asset.name}*: `${asset.balance:,.2f}` {asset.currency.upper()}\n"
        txt += "\n"

    return f"""*ASSETS*

{txt}"""


def get_crypto_summary_text(crypto: List[CryptoObject], show_details: bool) -> str:
    by_institution: dict[str, List[CryptoObject]] = {}
    for acct in crypto:
        by_institution.setdefault(acct.institution_name, []).append(acct)

    txt = ""
    for institution, accts in by_institution.items():
        txt += f"{make_tag(institution, title=True)}\n"
        for acct in accts:
            if show_details:
                txt += f"*{acct.name}*\n"
                txt += f"Balance: `${acct.balance:,.2f}` {acct.currency.upper()}\n"
                txt += f"Last update: {acct.balance_as_of.strftime('%a, %b %d at %I:%M %p')}\n"
                txt += f"Status: {acct.status}\n\n"
            else:
                txt += f" • *{acct.name}*: `${acct.balance:,.2f}` {get_crypto_symbol(acct.currency)}\n"
        txt += "\n"
    return f"""*CRYPTO*

{txt}"""


async def handle_show_balances(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mask: int = SHOW_BALANCES,
    message_id: Optional[int] = None,
):
    """Shows all the Plaid accounts and its balances to the user."""
    lunch = get_lunch_client_for_chat_id(get_chat_id(update))

    msg = ""
    if is_show_balances(mask):
        accts = lunch.get_plaid_accounts()
        msg += get_accounts_summary_text(accts, is_show_details(mask))

    if is_show_assets(mask):
        assets = lunch.get_assets()
        msg += get_assets_summary_text(assets, is_show_details(mask))

    if is_show_crypto(mask):
        crypto = lunch.get_crypto()
        msg += get_crypto_summary_text(crypto, is_show_details(mask))

    if message_id:
        await context.bot.edit_message_text(
            chat_id=get_chat_id(update),
            message_id=message_id,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_accounts_buttons(mask),
        )
    else:
        await context.bot.send_message(
            chat_id=get_chat_id(update),
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_accounts_buttons(mask),
        )


async def handle_btn_accounts_balances(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handles the button press to show the balances of the accounts."""
    mask = int(update.callback_query.data.split("_")[1])
    if (
        not is_show_balances(mask)
        and not is_show_assets(mask)
        and not is_show_crypto(mask)
    ):
        # do not allow to hide all of them
        return await update.callback_query.answer()

    await handle_show_balances(
        update, context, mask=mask, message_id=update.callback_query.message.message_id
    )
