from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="LinkTelegramRequest")



@_attrs_define
class LinkTelegramRequest:
    """ 
        Attributes:
            telegram_token (str):
            telegram_id (str):
     """

    telegram_token: str
    telegram_id: str





    def to_dict(self) -> dict[str, Any]:
        telegram_token = self.telegram_token

        telegram_id = self.telegram_id


        field_dict: dict[str, Any] = {}

        field_dict.update({
            "telegramToken": telegram_token,
            "telegramId": telegram_id,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        telegram_token = d.pop("telegramToken")

        telegram_id = d.pop("telegramId")

        link_telegram_request = cls(
            telegram_token=telegram_token,
            telegram_id=telegram_id,
        )

        return link_telegram_request

