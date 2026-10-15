from decimal import Decimal

from django.utils import timezone

from .models import SystemConfig


def format_money(amount, symbol=None):
    if symbol is None:
        symbol = SystemConfig.load().currency_symbol
    return f"{symbol}{Decimal(amount or 0):,.2f}"


def format_quantity(value):
    """2.00 -> "2", 1.50 -> "1.5"."""
    if value is None:
        return ""
    text = f"{Decimal(value):f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def format_date(value):
    return f"{value:%B} {value.day}, {value.year}" if value else ""


def format_datetime(value):
    if not value:
        return ""
    local = timezone.localtime(value)
    return f"{local:%B} {local.day}, {local.year} {local:%I:%M %p}".replace(" 0", " ")
