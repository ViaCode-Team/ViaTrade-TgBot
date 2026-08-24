from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="ConfirmReminderDeliveryRequest")



@_attrs_define
class ConfirmReminderDeliveryRequest:
    """ 
        Attributes:
            user_id (int):
     """

    user_id: int





    def to_dict(self) -> dict[str, Any]:
        user_id = self.user_id


        field_dict: dict[str, Any] = {}

        field_dict.update({
            "userId": user_id,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        user_id = d.pop("userId")

        confirm_reminder_delivery_request = cls(
            user_id=user_id,
        )

        return confirm_reminder_delivery_request

