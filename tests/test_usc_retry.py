"""Test cases for USC API client retry behavior."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from usc_signal_bot.usc import AMSTERDAM_TZ, USCClient


@pytest.mark.asyncio
class TestUSCRetryBehavior:
    """Test cases for retry behavior on HTTP errors."""

    @pytest.fixture
    def client(self):
        """Create a USC client instance."""
        return USCClient()

    async def test_retry_on_400_error(self, client):
        """Test that API calls retry on 400 Bad Request."""
        # Mock the httpx client to raise 400 error twice, then succeed
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            if call_count < 3:
                # First two calls fail with 400
                response.status_code = 400
                response.text = "Bad Request"
                # Create a proper HTTPStatusError with a response
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
                # Third call succeeds
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

        # Should succeed after retries
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
                # First call fails with 429
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
                # Second call succeeds
                response.status_code = 200
                response.json.return_value = {"id": 123, "email": "test@usc.nl"}
                response.raise_for_status.return_value = None
            return response

        client.client.get = AsyncMock(side_effect=mock_get)
        client.auth = MagicMock()
        client.auth.token_type = "Bearer"
        client.auth.access_token = "token"

        # Should succeed after retry
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
                # First two calls fail with 500
                response.status_code = 500
                response.text = "Internal Server Error"
                request = MagicMock()
                request.url = "https://example.com/bookable-slots"
                error_response = MagicMock()
                error_response.status_code = 500
                error_response.text = "Internal Server Error"
                error_response.request = request
                error = httpx.HTTPStatusError(
                    "Internal Server Error", request=request, response=error_response
                )
                response.raise_for_status.side_effect = error
            else:
                # Third call succeeds
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
        client.auth = MagicMock()
        client.auth.token_type = "Bearer"
        client.auth.access_token = "token"

        # Should succeed after retries
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

        # Should succeed without retries
        result = await client.authenticate("test@usc.nl", "password")
        assert result is not None
        assert call_count == 1, "Should not retry on success"

    async def test_max_retries_exceeded(self, client):
        """Test that API calls fail after maximum retries."""
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Always fail with 400
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

        # Should fail after max retries (4 attempts total)
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
                # First call fails with network error
                raise httpx.NetworkError("Connection failed")
            else:
                # Second call succeeds
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

        # Should succeed after retry
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
                # First two calls return invalid data (linkedProductId is None)
                response.json.return_value = {
                    "data": [
                        {
                            "startDate": "2024-03-20T17:30:00.000Z",
                            "endDate": "2024-03-20T19:00:00.000Z",
                            "isAvailable": True,
                            "linkedProductId": None,  # Invalid - should be int
                            "bookableProductId": 123,
                        }
                    ],
                    "page": 1,
                    "count": 1,
                    "total": 1,
                    "pageCount": 1,
                }
            else:
                # Third call returns valid data
                response.json.return_value = {
                    "data": [
                        {
                            "startDate": "2024-03-20T17:30:00.000Z",
                            "endDate": "2024-03-20T19:00:00.000Z",
                            "isAvailable": True,
                            "linkedProductId": 456,  # Valid
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
        client.auth = MagicMock()
        client.auth.token_type = "Bearer"
        client.auth.access_token = "token"

        # Should succeed after retries
        date = datetime.now(AMSTERDAM_TZ)
        result = await client.get_slots(date)
        assert result is not None
        assert call_count == 3, f"Should retry twice then succeed, but got {call_count} calls"
        assert len(result.data) == 1
        assert result.data[0].linkedProductId == 456
