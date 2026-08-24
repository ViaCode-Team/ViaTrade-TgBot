from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.problem_details_errors import ProblemDetailsErrors





T = TypeVar("T", bound="ProblemDetails")



@_attrs_define
class ProblemDetails:
    """ 
        Example:
            {'type': 'https://httpstatuses.io/400', 'title': 'Validation Failed', 'status': 400, 'detail': 'One or more
                validation errors occurred.', 'instance': '/api/trades', 'code': 'validation_failed', 'traceId':
                '0HNABC123:00000001'}

        Attributes:
            type_ (str):
            title (str):
            status (int):
            detail (str):
            instance (str):
            code (str):
            trace_id (str):
            errors (ProblemDetailsErrors | Unset):
     """

    type_: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    trace_id: str
    errors: ProblemDetailsErrors | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.problem_details_errors import ProblemDetailsErrors
        type_ = self.type_

        title = self.title

        status = self.status

        detail = self.detail

        instance = self.instance

        code = self.code

        trace_id = self.trace_id

        errors: dict[str, Any] | Unset = UNSET
        if not isinstance(self.errors, Unset):
            errors = self.errors.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "type": type_,
            "title": title,
            "status": status,
            "detail": detail,
            "instance": instance,
            "code": code,
            "traceId": trace_id,
        })
        if errors is not UNSET:
            field_dict["errors"] = errors

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.problem_details_errors import ProblemDetailsErrors
        d = dict(src_dict)
        type_ = d.pop("type")

        title = d.pop("title")

        status = d.pop("status")

        detail = d.pop("detail")

        instance = d.pop("instance")

        code = d.pop("code")

        trace_id = d.pop("traceId")

        _errors = d.pop("errors", UNSET)
        errors: ProblemDetailsErrors | Unset
        if isinstance(_errors,  Unset):
            errors = UNSET
        else:
            errors = ProblemDetailsErrors.from_dict(_errors)




        problem_details = cls(
            type_=type_,
            title=title,
            status=status,
            detail=detail,
            instance=instance,
            code=code,
            trace_id=trace_id,
            errors=errors,
        )


        problem_details.additional_properties = d
        return problem_details

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
