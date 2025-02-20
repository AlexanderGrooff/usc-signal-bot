"""USC API client for gym reservations."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx
from dateparser import parse
from pydantic import BaseModel, field_serializer

# All chat-input dates are in Amsterdam timezone.
# All dates in the USC API are in UTC.
AMSTERDAM_TZ = ZoneInfo("Europe/Amsterdam")
UTC_TZ = ZoneInfo("UTC")


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

    @field_serializer("startDate", "endDate")
    def format_timestamp(self, value: datetime) -> str:
        return value.astimezone(UTC_TZ).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class BookingData(BaseModel):
    """USC booking data."""

    organizationId: Optional[str] = None
    memberId: int
    primaryPurchaseMessage: Optional[str] = None
    secondaryPurchaseMessage: Optional[str] = None
    params: BookingParams
    dateOfRegistration: Optional[str] = None


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

    async def get_slots(self, date: str | datetime) -> BookableSlotsResponse:
        """Get available slots for a date.

        Args:
            date: Date to get slots for (in Amsterdam timezone)

        Returns:
            BookableSlotsResponse: Available slots
        """
        if not self.auth:
            raise RuntimeError("Not authenticated")

        date = _parse_ams_date(date)

        # Convert to UTC for API request
        utc_date = date.astimezone(UTC_TZ)
        date_str = utc_date.strftime("%Y-%m-%d")

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
            raise RuntimeError(f"Error getting slots: {e}; response: {response.text}") from e
        data = response.json()

        # Convert the raw slots to BookableSlot objects
        slots = [BookableSlot(**slot) for slot in data["data"]]
        return BookableSlotsResponse(data=slots, **{k: v for k, v in data.items() if k != "data"})

    async def get_slots_for_booking(
        self, date: datetime | str, num_slots: int
    ) -> List[BookableSlot]:
        """Get the required number of slots for a booking at the specified date.

        Args:
            date: The date and time to get slots for
            num_slots: The number of slots needed

        Returns:
            List of available slots matching the requirements

        Raises:
            RuntimeError if not enough slots are available
        """
        date = _parse_ams_date(date)

        # Get all available slots for the time
        slots_response = await self.get_slots(date)
        grouped_slots = self.format_slots(slots_response.data)

        # Get slots for the specific time
        time_key = _to_dict_key(date)
        if time_key not in grouped_slots:
            raise RuntimeError(f"No slots available for {date}")

        available_slots = grouped_slots[time_key]
        if len(available_slots) < num_slots:
            raise RuntimeError(
                f"Not enough slots available. Need {num_slots} slots but only found {len(available_slots)}"
            )

        # Return exactly the number of slots needed
        return available_slots[:num_slots]

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
            headers={
                "Authorization": f"{self.auth.token_type} {self.auth.access_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logging.error(f"Error getting member: {e}")
            logging.error(f"Response: {response.text}")
            raise RuntimeError(f"Error getting member: {e}; response: {response.text}") from e
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
        # 2 members and the member making the booking
        assert len(members) <= 2, "Only 2 members can be invited to a slot"

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
            # json=booking_data.model_dump_json(),
            data=booking_data.model_dump_json(),  # type: ignore
            headers={
                "Authorization": f"{self.auth.token_type} {self.auth.access_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logging.error(f"Error booking slot: {e}")
            logging.error(f"Response: {response.text}")
            raise RuntimeError(
                f"Error booking slot: {e}; response: {response.text}; booking data: {booking_data.model_dump_json()}"
            ) from e
        return response.json()

    async def close(self) -> None:
        """Close the client."""
        await self.client.aclose()

    async def get_matching_slot(self, date: datetime) -> Optional[BookableSlot]:
        """Get the first matching slot for a date.

        Args:
            date: Date to get matching slot for (in Amsterdam timezone)

        Returns:
            Optional[BookableSlot]: Matching slot
        """
        # Ensure date has timezone info
        if date.tzinfo is None:
            date = date.replace(tzinfo=AMSTERDAM_TZ)
        elif date.tzinfo != AMSTERDAM_TZ:
            date = date.astimezone(AMSTERDAM_TZ)

        slots = await self.get_slots(date)
        grouped_slots = self.format_slots(slots.data)
        try:
            return grouped_slots[_to_dict_key(date)][0]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"No available slot found for {date}") from e

    def format_slots(self, slots: List[BookableSlot]) -> Dict[str, List[BookableSlot]]:
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
            copiedSlot = slot.model_copy()
            copiedSlot.startDate = offset_slot_date(copiedSlot.startDate)
            copiedSlot.endDate = offset_slot_date(copiedSlot.endDate)

            # Filter out slots that are not in the range of start/end times
            slot_time = copiedSlot.startDate.time()
            if slot_time < from_time or slot_time > until_time:
                continue

            if _to_dict_key(copiedSlot.startDate) not in grouped:
                grouped[_to_dict_key(copiedSlot.startDate)] = []
            grouped[_to_dict_key(copiedSlot.startDate)].append(copiedSlot)
        return dict(sorted(grouped.items()))


def offset_slot_date(date: datetime) -> datetime:
    """Offset a slot date and convert to Amsterdam timezone.

    Args:
        date_str: Date string
        date_offset: Date offset

    Returns:
        datetime: Formatted date in Amsterdam timezone
    """
    # Convert to Amsterdam timezone
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC_TZ)
    return date.astimezone(AMSTERDAM_TZ)


def _to_dict_key(date: datetime) -> str:
    """Convert a datetime to a dict key. Useful for grouping slots by date without timezone."""
    return date.strftime("%Y-%m-%d %H:%M")


def format_slot_date(date: datetime) -> str:
    """Format a slot date.

    Args:
        date: Date

    Returns:
        str: Formatted date
    """
    return date.strftime("%Y-%m-%d %H:%M")


def _parse_ams_date(date: str | datetime) -> datetime:
    """Parse a date string or datetime object and return an Amsterdam timezone datetime.

    Args:
        date: Date string or datetime object

    Returns:
        datetime: Amsterdam timezone datetime
    """
    if isinstance(date, str):
        parsed_date = parse(date, settings={"TIMEZONE": "Europe/Amsterdam"})
        if not parsed_date:
            raise RuntimeError(f"Failed to parse date '{date}'")
        return parsed_date.replace(tzinfo=AMSTERDAM_TZ)
    elif date.tzinfo is None:
        return date.replace(tzinfo=AMSTERDAM_TZ)
    else:
        return date
