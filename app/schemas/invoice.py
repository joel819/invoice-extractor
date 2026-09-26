"""The invoice schema every extraction must pass. Money is Decimal, never float."""
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, field_validator, model_validator

from app.schemas.money import parse_date, parse_money

CURRENCIES = {"EUR", "USD", "GBP", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "CAD", "AUD", "JPY", "NGN", "TRY"}

Money = Annotated[
    Decimal,
    BeforeValidator(parse_money),
    PlainSerializer(lambda d: f"{d.quantize(Decimal('0.01'))}", return_type=str),
]
Quantity = Annotated[Decimal, BeforeValidator(parse_money), PlainSerializer(lambda d: f"{d.normalize():f}", return_type=str)]
InvoiceDate = Annotated[date, BeforeValidator(parse_date)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Vendor(_Strict):
    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    tax_id: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=320)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v and ("@" not in v or " " in v):
            raise ValueError("not a valid email address")
        return v or None


class LineItem(_Strict):
    description: str = Field(min_length=1, max_length=500)
    quantity: Quantity = Field(gt=0)
    unit_price: Money = Field(ge=0)
    amount: Money


class Totals(_Strict):
    subtotal: Money
    discount: Money = Field(default=Decimal("0"), ge=0)
    tax: Money = Field(default=Decimal("0"), ge=0)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100, description="Percent, e.g. 21")
    total: Money


class Invoice(_Strict):
    invoice_number: str = Field(min_length=1, max_length=64)
    invoice_date: InvoiceDate
    due_date: InvoiceDate | None = None
    currency: str
    vendor: Vendor
    bill_to: str | None = Field(default=None, max_length=500)
    line_items: list[LineItem] = Field(min_length=1, max_length=500)
    totals: Totals

    @field_validator("currency", mode="before")
    @classmethod
    def _currency(cls, v: object) -> str:
        code = {"€": "EUR", "$": "USD", "£": "GBP"}.get(str(v).strip(), str(v).strip().upper())
        if code not in CURRENCIES:
            raise ValueError(f"unsupported currency {v!r}; expected an ISO code like EUR or USD")
        return code

    @model_validator(mode="after")
    def _dates_in_order(self) -> "Invoice":
        if self.due_date and self.due_date < self.invoice_date:
            raise ValueError("due_date is before invoice_date")
        return self
