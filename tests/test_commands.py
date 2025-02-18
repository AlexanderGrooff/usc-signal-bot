"""Test cases for USC Signal Bot commands."""

import unittest
from typing import List, Tuple

from usc_signal_bot.commands import BookTimeslotCommand
from usc_signal_bot.config import BookingMember, USCCreds


def create_test_creds(emails: List[str]) -> USCCreds:
    """Create test credentials with given email addresses."""
    return USCCreds(
        bookingMembers=[BookingMember(username=email, password=f"pass_{email}") for email in emails]
    )


def format_allocation(
    allocation: List[Tuple[BookingMember, List[str]]]
) -> List[Tuple[str, List[str]]]:
    """Format allocation for easier assertion checking."""
    return [(bm.username, members) for bm, members in allocation]


class TestBookingAllocation(unittest.TestCase):
    """Test cases for booking allocation logic."""

    def setUp(self):
        """Set up test cases."""
        self.command = BookTimeslotCommand(
            create_test_creds(["john@usc.nl", "sarah@usc.nl", "mike@usc.nl"])
        )

    def test_single_member_without_credentials(self):
        """Test booking for a single member without credentials."""
        members = ["alice@usc.nl"]
        with self.assertRaises(RuntimeError) as context:
            self._allocate(members)
        self.assertTrue(
            "Not enough booking members available to book 1 squash courts"
            in str(context.exception),
            "Should raise error when not enough booking members",
        )

    def test_booking_member_uses_own_credentials(self):
        """Test that booking members use their own credentials when possible."""
        members = ["john@usc.nl"]
        allocation = self._allocate(members)
        self.assertEqual(
            allocation,
            [("john@usc.nl", [])],
            "John should book for himself",
        )

    def test_booking_member_book_for_others(self):
        """Test that booking members book for others when possible."""
        members = ["john@usc.nl", "alice@usc.nl"]
        allocation = self._allocate(members)
        self.assertEqual(
            allocation,
            [("john@usc.nl", ["alice@usc.nl"])],
            "John should book for himself and Alice",
        )

    def test_multiple_booking_members(self):
        """Test booking with multiple members who have credentials."""
        members = ["john@usc.nl", "sarah@usc.nl", "mike@usc.nl"]
        allocation = self._allocate(members)
        self.assertEqual(
            allocation,
            [
                ("john@usc.nl", ["sarah@usc.nl", "mike@usc.nl"]),
            ],
            "Three people should end up on one booking, even if they have credentials",
        )

    def test_mixed_booking_scenario(self):
        """Test booking with a mix of members with and without credentials."""
        members = ["john@usc.nl", "alice@usc.nl", "sarah@usc.nl", "bob@usc.nl"]
        allocation = self._allocate(members)
        self.assertEqual(
            allocation,
            [
                ("john@usc.nl", ["alice@usc.nl", "bob@usc.nl"]),
                ("sarah@usc.nl", []),
            ],
            "Members with credentials should book for themselves and others",
        )

    def test_mixed_booking_scenario_with_one_booking_member(self):
        """Test booking with a mix of members with and without credentials."""
        members = ["alice@usc.nl", "sarah@usc.nl", "bob@usc.nl"]
        allocation = self._allocate(members)
        self.assertEqual(
            allocation,
            [
                ("sarah@usc.nl", ["alice@usc.nl", "bob@usc.nl"]),
            ],
            "Members with credentials should book for themselves and others",
        )

    def test_not_enough_booking_members(self):
        """Test error when there aren't enough booking members."""
        members = ["alice@usc.nl", "bob@usc.nl", "charlie@usc.nl", "dave@usc.nl", "eve@usc.nl"]
        with self.assertRaises(RuntimeError) as context:
            self._allocate(members)
        self.assertTrue(
            "Not enough booking members available" in str(context.exception),
            "Should raise error when not enough booking members",
        )

    def _allocate(self, members: List[str]) -> List[Tuple[str, List[str]]]:
        """Helper method to allocate bookings and format results."""
        return format_allocation(self.command._allocate_bookings(members))


if __name__ == "__main__":
    unittest.main()
