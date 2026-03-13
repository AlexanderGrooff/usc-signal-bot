"""Test cases for USC API client retry behavior."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from usc_signal_bot.config import USCCreds
from usc_signal_bot.usc import AMSTERDAM_TZ, USCClient

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.mark.asyncio
class TestUSCRetryBehavior:
    """Test cases for retry behavior on HTTP errors."""

    @pytest.fixture
    def client(self):
        """Create a USC client instance."""
        return USCClient(
            USCCreds(bookingMembers=[], activityProductIds=[4637, 4638], userRoleId=34774)
        )

    async def test_retry_on_400_error(self, client):
        """Test that API calls retry on 400 Bad Request."""
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            if call_count < 3:
                response.status_code = 400
                response.text = "Bad Request"
                request = MagicMock()
                request.url = "https://example.com/auth"
                error_response = MagicMock()
                error_response.status_code = 400
                error_response.text = "Bad Request"
                error_response.request = request
                error = httpx.HTTPStatusError(
                    "Bad Request", request=request, response=error_response
                )
                response.raise_for_status.side_effect = error
            else:
                response.status_code = 200
                response.json.return_value = {
                    "access_token": "token",
                    "token_type": "Bearer",
                    "refresh_token": "refresh",
                    "scope": "scope",
                    "id_token": "id",
                    "expires_in": "3600",
                }
                response.raise_for_status.return_value = None
            return response

        client.client.post = AsyncMock(side_effect=mock_post)

        result = await client.authenticate("test@usc.nl", "password")
        assert result is not None
        assert call_count == 3, f"Should retry twice then succeed, but got {call_count} calls"

    async def test_retry_on_429_rate_limit(self, client):
        """Test that API calls retry on 429 Rate Limit."""
        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            if call_count < 2:
                response.status_code = 429
                response.text = "Too Many Requests"
                request = MagicMock()
                request.url = "https://example.com/auth"
                error_response = MagicMock()
                error_response.status_code = 429
                error_response.text = "Too Many Requests"
                error_response.request = request
                error = httpx.HTTPStatusError(
                    "Too Many Requests", request=request, response=error_response
                )
                response.raise_for_status.side_effect = error
            else:
                response.status_code = 200
                response.json.return_value = {"id": 123, "email": "test@usc.nl"}
                response.raise_for_status.return_value = None
            return response

        client.client.get = AsyncMock(side_effect=mock_get)
        client.auth = MagicMock(token_type="Bearer", access_token="token")

        result = await client.get_member()
        assert result is not None
        assert call_count == 2, f"Should retry once then succeed, but got {call_count} calls"

    async def test_retry_on_500_server_error(self, client):
        """Test that API calls retry on 500 Internal Server Error."""
        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            if call_count < 3:
                response.status_code = 500
                response.text = "Internal Server Error"
                request = MagicMock()
                request.url = "https://example.com/products/bookable-slots"
                error_response = MagicMock()
                error_response.status_code = 500
                error_response.text = "Internal Server Error"
                error_response.request = request
                error = httpx.HTTPStatusError(
                    "Internal Server Error", request=request, response=error_response
                )
                response.raise_for_status.side_effect = error
            else:
                response.status_code = 200
                response.json.return_value = {
                    "data": [],
                    "page": 1,
                    "count": 0,
                    "total": 0,
                    "pageCount": 0,
                }
                response.raise_for_status.return_value = None
            return response

        client.client.get = AsyncMock(side_effect=mock_get)
        client.auth = MagicMock(token_type="Bearer", access_token="token")

        date = datetime.now(AMSTERDAM_TZ)
        result = await client.get_slots(date)
        assert result is not None
        assert call_count == 3, f"Should retry twice then succeed, but got {call_count} calls"

    async def test_no_retry_on_success(self, client):
        """Test that successful API calls don't retry."""
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "access_token": "token",
                "token_type": "Bearer",
                "refresh_token": "refresh",
                "scope": "scope",
                "id_token": "id",
                "expires_in": "3600",
            }
            return response

        client.client.post = AsyncMock(side_effect=mock_post)

        result = await client.authenticate("test@usc.nl", "password")
        assert result is not None
        assert call_count == 1, "Should not retry on success"

    async def test_max_retries_exceeded(self, client):
        """Test that API calls fail after maximum retries."""
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            response.status_code = 400
            response.text = "Bad Request"
            request = MagicMock()
            request.url = "https://example.com/auth"
            error_response = MagicMock()
            error_response.status_code = 400
            error_response.text = "Bad Request"
            error_response.request = request
            error = httpx.HTTPStatusError("Bad Request", request=request, response=error_response)
            response.raise_for_status.side_effect = error
            return response

        client.client.post = AsyncMock(side_effect=mock_post)

        with pytest.raises(RuntimeError):
            await client.authenticate("test@usc.nl", "password")
        assert (
            call_count == 4
        ), f"Should attempt 4 times before giving up, but got {call_count} calls"

    async def test_retry_on_network_error(self, client):
        """Test that API calls retry on network errors."""
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.NetworkError("Connection failed")

            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "access_token": "token",
                "token_type": "Bearer",
                "refresh_token": "refresh",
                "scope": "scope",
                "id_token": "id",
                "expires_in": "3600",
            }
            return response

        client.client.post = AsyncMock(side_effect=mock_post)

        result = await client.authenticate("test@usc.nl", "password")
        assert result is not None
        assert call_count == 2, "Should retry once then succeed"

    async def test_retry_on_validation_error(self, client):
        """Test that API calls retry on Pydantic ValidationError (invalid data)."""
        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            response.status_code = 200
            response.raise_for_status.return_value = None
            if call_count < 3:
                response.json.return_value = {
                    "data": [
                        {
                            "startDate": "2024-03-20T17:30:00.000Z",
                            "endDate": "2024-03-20T19:00:00.000Z",
                            "isAvailable": True,
                            "linkedProductId": None,
                            "bookableProductId": 123,
                        }
                    ],
                    "page": 1,
                    "count": 1,
                    "total": 1,
                    "pageCount": 1,
                }
            else:
                response.json.return_value = {
                    "data": [
                        {
                            "startDate": "2024-03-20T17:30:00.000Z",
                            "endDate": "2024-03-20T19:00:00.000Z",
                            "isAvailable": True,
                            "linkedProductId": 456,
                            "bookableProductId": 123,
                        }
                    ],
                    "page": 1,
                    "count": 1,
                    "total": 1,
                    "pageCount": 1,
                }
            return response

        client.client.get = AsyncMock(side_effect=mock_get)
        client.auth = MagicMock(token_type="Bearer", access_token="token")

        date = datetime.now(AMSTERDAM_TZ)
        result = await client.get_slots(date)
        assert result is not None
        assert call_count == 3, f"Should retry twice then succeed, but got {call_count} calls"
        assert len(result.data) == 1
        assert result.data[0].linkedProductId == 456

    async def test_validation_error_contains_structured_slot_details(self, client):
        """Test that invalid slot errors include compact debugging details."""
        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            response.status_code = 200
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "data": [
                    {
                        "startDate": "2024-03-20T17:30:00.000Z",
                        "endDate": "2024-03-20T19:00:00.000Z",
                        "isAvailable": True,
                        "linkedProductId": None,
                        "bookableProductId": 123,
                        "linkedProduct": {
                            "id": 999,
                            "description": "Unexpected payload shape from USC",
                        },
                    }
                ],
                "page": 1,
                "count": 1,
                "total": 1,
                "pageCount": 1,
            }
            return response

        client.client.get = AsyncMock(side_effect=mock_get)
        client.auth = MagicMock(token_type="Bearer", access_token="token")

        date = datetime.now(AMSTERDAM_TZ)

        with pytest.raises(RuntimeError) as exc_info:
            await client.get_slots(date)

        message = str(exc_info.value)
        assert (
            call_count == 4
        ), f"Should attempt 4 times before giving up, but got {call_count} calls"
        assert "Invalid slot data received from API" in message
        assert "linkedProductId" in message
        assert "value=None" in message
        assert "all 1 slot(s) were invalid" in message
        assert "response_summary=count=1, total=1, page=1, pageCount=1, slot_count=1" in message
        assert "slot_index=0:" in message
        assert "slot_preview={'startDate': '2024-03-20T17:30:00.000Z'" in message

    async def test_mixed_valid_and_invalid_slots_returns_valid_ones(self, client):
        """Test that invalid slots are skipped when the response still contains valid slots."""
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": [
                {
                    "startDate": "2024-03-20T17:30:00.000Z",
                    "endDate": "2024-03-20T18:14:00.000Z",
                    "isAvailable": True,
                    "linkedProductId": None,
                    "bookableProductId": 123,
                },
                {
                    "startDate": "2024-03-20T17:30:00.000Z",
                    "endDate": "2024-03-20T18:14:00.000Z",
                    "isAvailable": True,
                    "linkedProductId": 456,
                    "bookableProductId": 124,
                },
            ],
            "page": 1,
            "count": 2,
            "total": 2,
            "pageCount": 1,
        }

        client.client.get = AsyncMock(return_value=response)
        client.auth = MagicMock(token_type="Bearer", access_token="token")

        date = datetime.now(AMSTERDAM_TZ)
        result = await client.get_slots(date)

        assert len(result.data) == 1
        assert result.data[0].linkedProductId == 456
        assert result.count == 2

    async def test_get_slots_uses_new_bookable_slots_endpoint_and_headers(self, client):
        """Test slot lookup calls the new endpoint with configured headers and filters."""
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = json.loads((FIXTURES_DIR / "bookable-slots.json").read_text())

        client.client.get = AsyncMock(return_value=response)
        client.auth = MagicMock(token_type="Bearer", access_token="token")

        date = datetime(2026, 3, 18, 18, 0, tzinfo=AMSTERDAM_TZ)
        result = await client.get_slots(date)

        assert result.data
        client.client.get.assert_awaited_once()
        _, kwargs = client.client.get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer token"
        assert kwargs["headers"]["x-platform"] == "CF"
        assert kwargs["headers"]["x-custom-lang"] == "en"
        assert kwargs["headers"]["x-user-role-id"] == "34774"
        assert kwargs["params"]["s"]
        query = json.loads(kwargs["params"]["s"])
        assert query["activityProductIds"]["$in"] == [4637, 4638]
        assert "$gte" in query["startDate"]
        assert "$lte" in query["endDate"]

    async def test_book_slot_surfaces_usc_member_lookup_error(self, client):
        """Test booking failures expose USC's actionable error message."""
        request = MagicMock()
        request.url = "https://example.com/participations"
        error_payload = json.loads((FIXTURES_DIR / "participations-fail.json").read_text())
        error_response = MagicMock()
        error_response.status_code = 403
        error_response.text = json.dumps(error_payload)
        error_response.json.return_value = error_payload
        error_response.request = request
        error = httpx.HTTPStatusError("Forbidden", request=request, response=error_response)

        response = MagicMock()
        response.raise_for_status.side_effect = error
        response.text = error_response.text
        response.json.return_value = error_payload

        client.client.post = AsyncMock(return_value=response)
        client.auth = MagicMock(token_type="Bearer", access_token="token")

        booking_data = client.create_booking_data(
            123,
            ["test@testing.nl"],
            MagicMock(
                linkedProductId=4637,
                bookableProductId=45,
                startDate=datetime(2026, 3, 18, 17, 45, tzinfo=AMSTERDAM_TZ),
                endDate=datetime(2026, 3, 18, 18, 29, tzinfo=AMSTERDAM_TZ),
            ),
        )

        with pytest.raises(RuntimeError) as exc_info:
            await client.book_slot(booking_data)

        message = str(exc_info.value)
        assert (
            "Sorry, unable to book activity, no member found for email test@testing.nl" in message
        )
        assert "booking data" in message
