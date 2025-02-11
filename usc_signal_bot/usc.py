"""USC API client for gym reservations."""

from dateparser import parse
from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, ConfigDict


class Auth(BaseModel):
    """USC authentication response."""

    scope: str
    id_token: str
    expires_in: str
    token_type: str
    access_token: str
    refresh_token: str



class Member(BaseModel):
    """USC member information."""

    id: int
    email: str


class BookableSlot(BaseModel):
    """USC bookable slot information."""

    startDate: str
    endDate: str
    isAvailable: bool
    linkedProductId: int  # Timeslot
    bookableProductId: int  # Squash court number



class BookableSlotsResponse(BaseModel):
    """USC bookable slots response."""

    data: List[BookableSlot]
    page: int
    count: int
    total: int
    pageCount: int



class BookingParams(BaseModel):
    """USC booking parameters."""

    bookableLinkedProductId: int
    bookableProductId: int
    clickedOnBook: bool
    startDate: str
    endDate: str
    invitedGuests: List[str]
    invitedMemberEmails: List[str]
    invitedOthers: List[str]
    secondaryPurchaseMessage: Optional[str] = None
    primaryPurchaseMessage: Optional[str] = None



class BookingData(BaseModel):
    """USC booking data."""

    memberId: int
    params: BookingParams
    dateOfRegistration: Optional[str] = None
    organizationId: Optional[str] = None
    secondaryPurchaseMessage: Optional[str] = None
    primaryPurchaseMessage: Optional[str] = None


class USCClient:
    """USC API client."""

    BASE_URL = "https://backbone-web-api.production.uva.delcom.nl"

    def __init__(self) -> None:
        """Initialize the USC client."""
        self.client = httpx.AsyncClient(base_url=self.BASE_URL)
        self.auth: Optional[Auth] = None

    async def authenticate(self, username: str, password: str) -> Auth:
        """Authenticate with USC.

        Args:
            username: USC username/email
            password: USC password

        Returns:
            Auth: Authentication response
        """
        response = await self.client.post(
            "/auth",
            json={"email": username, "password": password},
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        self.auth = Auth(**response.json())
        logging.info(f"Authenticated with USC: {self.auth}")
        return self.auth

    async def get_slots(self, date: datetime) -> BookableSlotsResponse:
        """Get available slots for a date.

        Args:
            date: Date to get slots for

        Returns:
            BookableSlotsResponse: Available slots
        """
        if not self.auth:
            raise RuntimeError("Not authenticated")

        next_week_wednesday = parse("6 days later")
        if not next_week_wednesday:
            raise RuntimeError("Failed to parse 6 days from now")
        date_str = next_week_wednesday.strftime("%Y-%m-%d")
        from_time = "00:00:00.000"
        until_time = "23:00:00.000"

        logging.info(f"Getting slots from {date_str}T{from_time}Z to {date_str}T{until_time}Z")
        params = {
            "s": json.dumps({
                "startDate": f"{date_str}T{from_time}Z",
                "endDate": f"{date_str}T{until_time}Z",
                "tagIds": {"$in": [195]},
                "availableFromDate": {"$gt": f"{date_str}T{from_time}Z"},
                "availableTillDate": {"$lte": f"{date_str}T{until_time}Z"},
            }),
            "join": json.dumps([
                "linkedProduct",
                "linkedProduct.translations",
                "product",
                "product.translations",
            ]),
        }

        response = await self.client.get(
            "/bookable-slots",
            params=params,
            headers={"Authorization": f"{self.auth.token_type} {self.auth.access_token}", "Content-Type": "application/json"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logging.error(f"Error getting slots: {e}")
            logging.error(f"Response: {response.text}")
            raise e
        data = response.json()

        # Convert the raw slots to BookableSlot objects
        slots = [BookableSlot(**slot) for slot in data["data"]]
        return BookableSlotsResponse(data=slots, **{k: v for k, v in data.items() if k != "data"})

    async def get_member(self) -> Member:
        """Get the current member's information.

        Returns:
            Member: Member information
        """
        if not self.auth:
            raise RuntimeError("Not authenticated")

        response = await self.client.get(
            "/auth",
            params={"cf": 0},
            headers={"Authorization": f"{self.auth.token_type} {self.auth.access_token}"},
        )
        response.raise_for_status()
        return Member(**response.json())

    def create_booking_data(self, member_id: int, members: List[str], slot: BookableSlot) -> BookingData:
        """Create booking data for a slot.

        Args:
            member_id: Member ID making the booking
            members: List of member emails to invite
            slot: Slot to book

        Returns:
            BookingData: Booking data
        """
        return BookingData(
            memberId=member_id,
            params=BookingParams(
                bookableLinkedProductId=slot.linkedProductId,
                bookableProductId=slot.bookableProductId,
                clickedOnBook=True,
                startDate=slot.startDate,
                endDate=slot.endDate,
                invitedGuests=[],
                invitedMemberEmails=members,
                invitedOthers=[],
            ),
        )

    async def book_slot(self, booking_data: BookingData) -> Dict[str, Any]:
        """Book a slot.

        Args:
            booking_data: Booking data

        Returns:
            Dict[str, Any]: Booking response
        """
        if not self.auth:
            raise RuntimeError("Not authenticated")

        response = await self.client.post(
            "/participations",
            json=booking_data.model_dump(by_alias=True),
            headers={"Authorization": f"{self.auth.token_type} {self.auth.access_token}"},
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        """Close the client."""
        await self.client.aclose() 