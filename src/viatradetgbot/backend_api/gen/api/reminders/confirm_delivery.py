from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.confirm_reminder_delivery_request import ConfirmReminderDeliveryRequest
from ...models.problem_details import ProblemDetails
from typing import cast



def _get_kwargs(
    reminder_id: int,
    *,
    body: ConfirmReminderDeliveryRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/v1/internal/tgbot/reminders/{reminder_id}/delivery".format(reminder_id=quote(str(reminder_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | ProblemDetails | None:
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

    if response.status_code == 400:
        response_400 = ProblemDetails.from_dict(response.json())



        return response_400

    if response.status_code == 401:
        response_401 = ProblemDetails.from_dict(response.json())



        return response_401

    if response.status_code == 403:
        response_403 = ProblemDetails.from_dict(response.json())



        return response_403

    if response.status_code == 404:
        response_404 = ProblemDetails.from_dict(response.json())



        return response_404

    if response.status_code == 408:
        response_408 = ProblemDetails.from_dict(response.json())



        return response_408

    if response.status_code == 409:
        response_409 = ProblemDetails.from_dict(response.json())



        return response_409

    if response.status_code == 422:
        response_422 = ProblemDetails.from_dict(response.json())



        return response_422

    if response.status_code == 500:
        response_500 = ProblemDetails.from_dict(response.json())



        return response_500

    if response.status_code == 503:
        response_503 = ProblemDetails.from_dict(response.json())



        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any | ProblemDetails]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    reminder_id: int,
    *,
    client: AuthenticatedClient,
    body: ConfirmReminderDeliveryRequest,

) -> Response[Any | ProblemDetails]:
    """ 
    Args:
        reminder_id (int):
        body (ConfirmReminderDeliveryRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ProblemDetails]
     """


    kwargs = _get_kwargs(
        reminder_id=reminder_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    reminder_id: int,
    *,
    client: AuthenticatedClient,
    body: ConfirmReminderDeliveryRequest,

) -> Any | ProblemDetails | None:
    """ 
    Args:
        reminder_id (int):
        body (ConfirmReminderDeliveryRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ProblemDetails
     """


    return sync_detailed(
        reminder_id=reminder_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    reminder_id: int,
    *,
    client: AuthenticatedClient,
    body: ConfirmReminderDeliveryRequest,

) -> Response[Any | ProblemDetails]:
    """ 
    Args:
        reminder_id (int):
        body (ConfirmReminderDeliveryRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ProblemDetails]
     """


    kwargs = _get_kwargs(
        reminder_id=reminder_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    reminder_id: int,
    *,
    client: AuthenticatedClient,
    body: ConfirmReminderDeliveryRequest,

) -> Any | ProblemDetails | None:
    """ 
    Args:
        reminder_id (int):
        body (ConfirmReminderDeliveryRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ProblemDetails
     """


    return (await asyncio_detailed(
        reminder_id=reminder_id,
client=client,
body=body,

    )).parsed
