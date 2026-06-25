from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Contractor:
    id: str
    name: str
    inn: str = ""
    kpp: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    bank: str = ""
    bik: str = ""
    account: str = ""
    corr_account: str = ""
    comment: str = ""
    markup_percent: float = 0.0
    currency: str = "руб."
    is_default: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Contractor":
        return cls(
            id=str(data.get("id", "")) or _slug(str(data.get("name", "default"))),
            name=str(data.get("name", "По умолчанию")),
            inn=str(data.get("inn", "")),
            kpp=str(data.get("kpp", "")),
            phone=str(data.get("phone", "")),
            email=str(data.get("email", "")),
            address=str(data.get("address", "")),
            bank=str(data.get("bank", "")),
            bik=str(data.get("bik", "")),
            account=str(data.get("account", "")),
            corr_account=str(data.get("corr_account", "")),
            comment=str(data.get("comment", "")),
            markup_percent=float(data.get("markup_percent", 0.0) or 0.0),
            currency=str(data.get("currency", "руб.")),
            is_default=bool(data.get("is_default", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "inn": self.inn,
            "kpp": self.kpp,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "bank": self.bank,
            "bik": self.bik,
            "account": self.account,
            "corr_account": self.corr_account,
            "comment": self.comment,
            "markup_percent": self.markup_percent,
            "currency": self.currency,
            "is_default": self.is_default,
        }


def contractors_from_settings(settings: dict[str, Any]) -> list[Contractor]:
    rows = settings.get("contractors", [])
    contractors = [Contractor.from_dict(row) for row in rows if isinstance(row, dict)]
    if not contractors:
        contractors = [Contractor(id="default", name="По умолчанию", is_default=True)]
    if not any(item.is_default for item in contractors):
        contractors[0].is_default = True
    return contractors


def default_contractor(settings: dict[str, Any]) -> Contractor:
    contractors = contractors_from_settings(settings)
    return next((item for item in contractors if item.is_default), contractors[0])


def contractor_by_name(settings: dict[str, Any], name: str) -> Contractor:
    contractors = contractors_from_settings(settings)
    return next((item for item in contractors if item.name == name), default_contractor(settings))


def _slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    return slug or "default"
