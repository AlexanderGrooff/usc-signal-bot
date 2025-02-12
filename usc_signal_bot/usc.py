"""USC API client for gym reservations."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from dateparser import parse
from pydantic import BaseModel


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

    startDate: datetime
    endDate: datetime
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
    startDate: datetime
    endDate: datetime
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
    FROM_TIME = "17:30:00.000"
    UNTIL_TIME = "19:00:00.000"

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

    async def get_slots(self, natural_date: str) -> BookableSlotsResponse:
        """Get available slots for a date.

        Args:
            date: Date to get slots for

        Returns:
            BookableSlotsResponse: Available slots
        """
        if not self.auth:
            raise RuntimeError("Not authenticated")

        date = parse(natural_date)
        if not date:
            raise RuntimeError(f"Failed to parse date '{natural_date}'")

        date_str = date.strftime("%Y-%m-%d")

        logging.info(
            f"Getting slots from {date_str}T{self.FROM_TIME}Z to {date_str}T{self.UNTIL_TIME}Z"
        )
        params = {
            "s": json.dumps(
                {
                    "startDate": f"{date_str}T{self.FROM_TIME}Z",
                    "endDate": f"{date_str}T{self.UNTIL_TIME}Z",
                    "tagIds": {"$in": [195]},
                }
            ),
            "join": json.dumps(
                [
                    "linkedProduct",
                    "product",
                ]
            ),
        }

        response = await self.client.get(
            "/bookable-slots",
            params=params,
            headers={
                "Authorization": f"{self.auth.token_type} {self.auth.access_token}",
                "Content-Type": "application/json",
            },
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

    def create_booking_data(
        self, member_id: int, members: List[str], slot: BookableSlot
    ) -> BookingData:
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

    def format_slots(
        self, slots: List[BookableSlot], date_offset: timedelta | None = None
    ) -> Dict[datetime, List[BookableSlot]]:
        """Group slots by start time, filter out unavailable slots, and format the dates.

        Args:
            slots: List of slots

        Returns:
            Dict[str, List[BookableSlot]]: Grouped slots, sorted by start date
        """
        grouped = {}
        from_time = datetime.strptime(self.FROM_TIME, "%H:%M:%S.%f").time()
        until_time = datetime.strptime(self.UNTIL_TIME, "%H:%M:%S.%f").time()
        for slot in slots:
            if not slot.isAvailable:
                continue
            slot.startDate = offset_slot_date(slot.startDate, date_offset)
            slot.endDate = offset_slot_date(slot.endDate, date_offset)

            # Filter out slots that are not in the range of start/end times
            slot_time = slot.startDate.time()
            if slot_time < from_time or slot_time > until_time:
                continue

            if slot.startDate not in grouped:
                grouped[slot.startDate] = []
            grouped[slot.startDate].append(slot)
        return dict(sorted(grouped.items()))


def offset_slot_date(date: datetime, date_offset: timedelta | None = None) -> datetime:
    """Offset a slot date.

    Args:
        date_str: Date string
        date_offset: Date offset

    Returns:
        datetime: Formatted date
    """
    # There seems to be an offset of 15 minutes in the startDate. No idea why.
    date_offset = date_offset or timedelta(minutes=15)
    return date + date_offset


def format_slot_date(date: datetime) -> str:
    """Format a slot date.

    Args:
        date: Date

    Returns:
        str: Formatted date
    """
    return date.strftime("%Y-%m-%d %H:%M")
