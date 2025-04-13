"""Test cases for USC Signal Bot commands."""

import unittest
from typing import List, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

from signalbot import Context

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
            self._allocate(members, 1)
        self.assertTrue(
            "Not enough authenticated booking members available to book 1 squash courts"
            in str(context.exception),
            "Should raise error when not enough booking members",
        )

    def test_booking_member_uses_own_credentials(self):
        """Test that booking members use their own credentials when possible."""
        members = ["john@usc.nl"]
        allocation = self._allocate(members, 1)
        self.assertEqual(
            allocation,
            [("john@usc.nl", [])],
            "John should book for himself",
        )

    def test_booking_member_book_for_others(self):
        """Test that booking members book for others when possible."""
        members = ["john@usc.nl", "alice@usc.nl"]
        allocation = self._allocate(members, 1)
        self.assertEqual(
            allocation,
            [("john@usc.nl", ["alice@usc.nl"])],
            "John should book for himself and Alice",
        )

    def test_multiple_booking_members(self):
        """Test booking with multiple members who have credentials."""
        members = ["john@usc.nl", "sarah@usc.nl", "mike@usc.nl"]
        allocation = self._allocate(members, 1)
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
        allocation = self._allocate(members, 2)
        self.assertEqual(
            allocation,
            [
                ("john@usc.nl", ["alice@usc.nl"]),
                ("sarah@usc.nl", ["bob@usc.nl"]),
            ],
            "Members with credentials should book for themselves and others",
        )

    def test_mixed_booking_scenario_with_one_booking_member(self):
        """Test booking with a mix of members with and without credentials."""
        members = ["alice@usc.nl", "sarah@usc.nl", "bob@usc.nl"]
        allocation = self._allocate(members, 1)
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
            self._allocate(members, 2)
        self.assertTrue(
            "Not enough authenticated booking members available" in str(context.exception),
            "Should raise error when not enough booking members",
        )

    def test_max_players_per_court_should_be_four(self):
        members = ["alice@usc.nl", "bob@usc.nl", "sarah@usc.nl", "henk@usc.nl"]
        allocation = self._allocate(members, 1)
        self.assertEqual(
            allocation,
            [
                ("sarah@usc.nl", ["alice@usc.nl", "bob@usc.nl", "henk@usc.nl"]),
            ],
            "Members with credentials should book for themselves and others",
        )

    def test_players_exeeding_max_players_per_court(self):
        members = ["alice@usc.nl", "bob@usc.nl", "sarah@usc.nl", "henk@usc.nl", "bert@usc.nl"]
        with self.assertRaises(RuntimeError) as context:
            self._allocate(members, 1)
        self.assertTrue(
            "Requested 1 courts, but at least 2 are needed for 5 players" in str(context.exception),
            "Should rause error when too many players per court",
        )

    def test_players_can_book_more_courts_then_needed(self):
        """
        Let's say someone wants 3 courts for 6 players.
        """
        members = [
            "alice@usc.nl",
            "bob@usc.nl",
            "sarah@usc.nl",
            "john@usc.nl",
            "mike@usc.nl",
            "henk@usc.nl",
        ]
        allocation = self._allocate(members, 3)
        self.assertEqual(
            allocation,
            [
                ("john@usc.nl", ["alice@usc.nl"]),
                ("sarah@usc.nl", ["bob@usc.nl"]),
                ("mike@usc.nl", ["henk@usc.nl"]),
            ],
            "Members with credentials should book for themselves and others",
        )

    def _allocate(self, members: List[str], courts: int) -> List[Tuple[str, List[str]]]:
        """Helper method to allocate bookings and format results."""
        return format_allocation(self.command._allocate_bookings(members, courts))


class TestArgumentParsing(unittest.TestCase):
    """Test cases for argument parsing."""

    def setUp(self):
        """Set up test cases."""
        self.command = BookTimeslotCommand(
            create_test_creds(["john@usc.nl", "sarah@usc.nl", "mike@usc.nl"])
        )

    def test_basic_booking_command(self):
        """Test parsing a basic booking command."""
        args = self.command._parse_args("book 1 2024-03-20 18:00 john@usc.nl alice@usc.nl")
        self.assertIsNotNone(args, "Arguments should be parsed successfully")
        self.assertFalse(args.dry_run)  # type: ignore
        self.assertEqual(args.courts, 1)  # type: ignore
        self.assertEqual(args.date, "2024-03-20")  # type: ignore
        self.assertEqual(args.time, "18:00")  # type: ignore
        self.assertEqual(args.members, ["john@usc.nl", "alice@usc.nl"])  # type: ignore

    def test_dry_run_flag(self):
        """Test parsing a command with dry-run flag."""
        args = self.command._parse_args("book --dry-run 1 2024-03-20 18:00 john@usc.nl")
        self.assertIsNotNone(args, "Arguments should be parsed successfully")
        self.assertTrue(args.dry_run)  # type: ignore
        self.assertEqual(args.date, "2024-03-20")  # type: ignore
        self.assertEqual(args.time, "18:00")  # type: ignore
        self.assertEqual(args.members, ["john@usc.nl"])  # type: ignore

    def test_help_request(self):
        """Test help request returns None."""
        self.assertIsNone(self.command._parse_args("book --help"))
        self.assertIsNone(self.command._parse_args("book -h"))

    def test_invalid_command(self):
        """Test invalid command raises error."""
        with self.assertRaises(RuntimeError):
            self.command._parse_args("book")  # Missing required arguments

    def test_quoted_emails(self):
        """Test handling of quoted email addresses."""
        args = self.command._parse_args(
            'book 1 2024-03-20 18:00 "john@usc.nl" "user with spaces@usc.nl"'
        )
        self.assertIsNotNone(args, "Arguments should be parsed successfully")
        self.assertEqual(args.members, ["john@usc.nl", "user with spaces@usc.nl"])  # type: ignore


@patch("usc_signal_bot.commands.parse")
class TestBookingCommand(unittest.TestCase):
    """Test cases for the booking command handler."""

    def setUp(self):
        """Set up test cases."""
        self.command = BookTimeslotCommand(
            create_test_creds(["john@usc.nl", "sarah@usc.nl", "mike@usc.nl"])
        )
        self.context = MagicMock(spec=Context)
        self.context.send = AsyncMock()

    async def test_help_message(self, mock_parse):
        """Test help message is shown."""
        self.context.message.text = "book --help"
        await self.command.handle(self.context)
        self.context.send.assert_called_once()
        help_text = self.context.send.call_args[0][0]
        self.assertIn("Book a timeslot at USC", help_text)

    @patch("usc_signal_bot.commands.USCClient")
    async def test_dry_run_booking(self, mock_usc_client, mock_parse):
        """Test dry run booking shows what would be booked."""
        # Setup mocks
        mock_parse.return_value = "2024-03-20 18:00"
        mock_client = AsyncMock()
        mock_usc_client.return_value = mock_client
        mock_client.get_matching_slot.return_value = MagicMock(
            startDate="2024-03-20 18:00", endDate="2024-03-20 19:00"
        )
        mock_client.get_member.return_value = MagicMock(id=123)

        # Test dry run
        self.context.message.text = "book --dry-run 2024-03-20 18:00 john@usc.nl alice@usc.nl"
        await self.command.handle(self.context)

        # Verify
        self.context.send.assert_called_once()
        response = self.context.send.call_args[0][0]
        self.assertIn("[DRY RUN]", response)
        self.assertIn("Would book slot", response)
        # Verify no actual booking was made
        mock_client.book_slot.assert_not_called()

    @patch("usc_signal_bot.commands.USCClient")
    async def test_actual_booking(self, mock_usc_client, mock_parse):
        """Test actual booking makes the API call."""
        # Setup mocks
        mock_parse.return_value = "2024-03-20 18:00"
        mock_client = AsyncMock()
        mock_usc_client.return_value = mock_client
        mock_client.get_matching_slot.return_value = MagicMock(
            startDate="2024-03-20 18:00", endDate="2024-03-20 19:00"
        )
        mock_client.get_member.return_value = MagicMock(id=123)

        # Test actual booking
        self.context.message.text = "book 2024-03-20 18:00 john@usc.nl alice@usc.nl"
        await self.command.handle(self.context)

        # Verify
        self.context.send.assert_called_once()
        response = self.context.send.call_args[0][0]
        self.assertNotIn("[DRY RUN]", response)
        self.assertIn("Booking successful", response)
        # Verify booking was made
        mock_client.book_slot.assert_called_once()


if __name__ == "__main__":
    unittest.main()
