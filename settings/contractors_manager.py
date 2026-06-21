from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Contractor:
    id: str
    name: str
    inn: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
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
            phone=str(data.get("phone", "")),
            email=str(data.get("email", "")),
            address=str(data.get("address", "")),
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
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
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
