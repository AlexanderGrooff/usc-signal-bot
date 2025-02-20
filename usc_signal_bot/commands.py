"""Signal bot commands."""

import asyncio
import logging
import math
import os
import re
import shlex
from argparse import ArgumentError, ArgumentParser, Namespace
from datetime import datetime
from functools import wraps
from typing import List, Optional

from dateparser import parse
from signalbot import Command, Context, triggered

from usc_signal_bot._version import __version__
from usc_signal_bot.config import BookingMember, USCCreds
from usc_signal_bot.usc import AMSTERDAM_TZ, USCClient, format_slot_date


def notify_error(func):
    @wraps(func)
    async def wrapper_notify_error(self, c: Context):
        try:
            return await func(self, c)
        except Exception as e:
            logging.exception(f"Error in {func.__name__}")
            await c.send(f"Error in {func.__name__}: {e}")

    return wrapper_notify_error


def ignore_unrelated_messages(start_word, case_sensitive=False):
    def decorator_ignore_unrelated_messages(func):
        @wraps(func)
        async def wrapper_ignore_unrelated_messages(self, c: Context):
            text = c.message.text
            if not isinstance(text, str):
                logging.debug(f"Ignoring unrelated message: {text}, expected {start_word}")
                return

            if not case_sensitive:
                text = text.lower()
            if not text.startswith(start_word):
                logging.info(f"Ignoring unrelated message: {text}, expected {start_word}")
                return

            return await func(self, c)

        return wrapper_ignore_unrelated_messages

    return decorator_ignore_unrelated_messages


def get_version() -> str:
    """Get the current version from package metadata."""
    return __version__


def get_hostname() -> str:
    """Get the hostname, preferring HOSTNAME env var over socket.gethostname()."""
    return os.getenv("HOSTNAME", "unknown")


class PingCommand(Command):
    """Simple ping command that responds with the current time."""

    def setup(self):
        logging.info("Setting up PingCommand")
        return super().setup()

    def describe(self) -> str:
        logging.info("Describing PingCommand")
        return super().describe()

    @notify_error
    @triggered("ping")
    async def handle(self, c: Context):
        logging.info(f"Received message: {c.message.text}")
        hostname = get_hostname()
        version = get_version()
        await c.send(f"Pong {datetime.now(AMSTERDAM_TZ)} - {hostname} - v{version}")


class GetTimeslotsCommand(Command):
    """Command to get available timeslots from USC."""

    def __init__(self, usc_creds: USCCreds):
        super().__init__()
        self.usc_creds = usc_creds
        self.message_pattern = re.compile(r"^timeslots(\s+\d{4}-\d{2}-\d{2})?$", re.IGNORECASE)

    def setup(self):
        logging.info("Setting up GetTimeslotsCommand")
        return super().setup()

    def describe(self) -> str:
        logging.info("Describing GetTimeslotsCommand")
        return super().describe()

    @ignore_unrelated_messages("timeslots")
    @notify_error
    async def handle(self, c: Context):
        match = self.message_pattern.match(c.message.text)
        if not match:
            await c.send(
                "Invalid message format. Please use the following format:\ntimeslots <date?>"
            )
            return
        logging.info(f"Received message: {c.message.text}")

        date_str = match.group(1)
        if date_str:
            date = parse(date_str.strip())
        else:
            # By default timeslots are released 6 days in advance
            date = parse("6 days later")
        if not date:
            await c.send("Invalid date format. Please use the following format:\ntimeslots <date?>")
            return

        if not self.usc_creds.bookingMembers:
            await c.send("No booking members configured")
            return

        # Use the first booking member's credentials
        booking_member = self.usc_creds.bookingMembers[0]
        usc = USCClient()
        await usc.authenticate(booking_member.username, booking_member.password)
        timeslots = await usc.get_slots(date)

        # Format the response
        grouped_slots = usc.format_slots(timeslots.data)
        available_slots = [
            f"- {format_slot_date(slots[0].startDate)} - {format_slot_date(slots[0].endDate)} - **{len(slots)} slots available**"
            for slots in grouped_slots.values()
        ]

        day_str = date.strftime("%A %Y-%m-%d")
        if available_slots:
            response = f"Available slots for **{day_str}**:\n" + "\n".join(available_slots)
        else:
            response = f"No available slots found for **{day_str}**"

        await c.send(response, text_mode="styled")
        await usc.close()


class BookTimeslotCommand(Command):
    """Command to book a timeslot from USC."""

    def __init__(self, usc_creds: USCCreds):
        super().__init__()
        self.usc_creds = usc_creds
        self.parser = self._create_parser()

    async def log(self, context: Context, message: str):
        logging.info(message)
        try:
            await context.send(message, text_mode="styled")
        except Exception as e:
            logging.exception(f"Error sending message: {e}")

    def _create_parser(self) -> ArgumentParser:
        """Create the argument parser for the book command."""
        parser = ArgumentParser(
            prog="book",
            description="Book a timeslot at USC",
            add_help=False,  # We'll handle help ourselves
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate booking without actually making the reservation",
        )
        parser.add_argument(
            "date",
            help="Date to book (YYYY-MM-DD)",
        )
        parser.add_argument(
            "time",
            help="Time to book (HH:MM)",
        )
        parser.add_argument(
            "members",
            nargs="+",
            help="Email addresses of members to book for",
        )
        return parser

    def setup(self):
        logging.info("Setting up BookTimeslotCommand")
        return super().setup()

    def describe(self) -> str:
        logging.info("Describing BookTimeslotCommand")
        return super().describe()

    async def _make_booking(
        self,
        date: datetime,
        members: List[str],
        booking_member: BookingMember,
        dry_run: bool = False,
    ) -> str:
        """Make a booking with a specific member's credentials.

        Args:
            date: Date to book
            members: List of member emails to invite (max 2)
            booking_member: Credentials to use for booking
            dry_run: If True, only simulate the booking without actually making it

        Returns:
            str: Booking response message
        """
        usc = USCClient()
        try:
            await usc.authenticate(booking_member.username, booking_member.password)
            slot = await usc.get_matching_slot(date)
            if not slot:
                raise RuntimeError(f"No available slot found on {date}")

            booking_member_info = await usc.get_member()
            booking_data = usc.create_booking_data(booking_member_info.id, members, slot=slot)

            if dry_run:
                return f"[DRY RUN] Would book slot {format_slot_date(slot.startDate)} - {format_slot_date(slot.endDate)} with {booking_member.username} for members {', '.join(members)}"

            await usc.book_slot(booking_data)
            return f"Booking successful with {booking_member.username} for members {', '.join(members)}"
        except Exception as e:
            return f"{'[DRY RUN] ' if dry_run else ''}Booking failed with {booking_member.username}: {str(e)}"
        finally:
            await usc.close()

    def _allocate_bookings(self, players: List[str]) -> List[tuple[BookingMember, List[str]]]:
        """Allocate booking members to groups of players.

        This function tries to match booking members with their emails when possible,
        and uses remaining booking members for other players.
        Note: A booking member must always be included in their own booking.

        Args:
            players: List of player emails to book for

        Returns:
            List of tuples containing (booking_member, list_of_members_to_book_for)
        """
        authenticated_players = [m for m in self.usc_creds.bookingMembers if m.username in players]
        allocations: List[tuple[BookingMember, List[str]]] = []
        remaining_players = players.copy()
        amount_of_bookings_required = math.ceil(len(players) / 3)  # 1 slot per 3 players
        amount_of_authenticated_players = len(authenticated_players)
        players_to_book = [m.username for m in authenticated_players][:amount_of_bookings_required]

        if amount_of_authenticated_players < amount_of_bookings_required:
            raise RuntimeError(
                f"Not enough booking members available to book {amount_of_bookings_required} squash courts"
            )

        # Allocate authenticated players to groups of 2 players
        for i in range(amount_of_bookings_required):
            booking_member = authenticated_players[i]
            current_group = []
            remaining_players.remove(booking_member.username)
            j = 0
            while len(remaining_players) > 0 and len(current_group) < 2:
                next_player = remaining_players[j]
                if next_player not in players_to_book:
                    current_group.append(next_player)
                    remaining_players.remove(next_player)
                    # j -= 1
                else:
                    j += 1
            allocations.append((booking_member, current_group))

        return allocations

    def _parse_args(self, text: str) -> Optional[Namespace]:
        """Parse command arguments from text.

        Args:
            text: Command text to parse

        Returns:
            Optional[Namespace]: Parsed arguments or None if help requested
        """
        # Remove the command name and split into args
        args_str = re.sub(r"^book\s+", "", text.strip(), flags=re.IGNORECASE)
        try:
            args = shlex.split(args_str)
            if "--help" in args or "-h" in args:
                return None
            return self.parser.parse_args(args)
        except (ArgumentError, ValueError, SystemExit) as e:
            raise RuntimeError(f"Error parsing arguments: {str(e)}") from e

    @ignore_unrelated_messages("book")
    @notify_error
    async def handle(self, c: Context):
        logging.info(f"Received message: {c.message.text}")

        try:
            args = self._parse_args(c.message.text)
            if args is None:
                # Help requested
                await self.log(c, self.parser.format_help())
                return

            date = parse(f"{args.date} {args.time}")
            if not date:
                raise RuntimeError(f"Failed to parse date '{args.date} {args.time}'")

            # Allocate bookings smartly
            allocations = self._allocate_bookings(args.members)

            # Make bookings in parallel
            booking_tasks = [
                self._make_booking(date, members_to_book, booking_member, args.dry_run)
                for booking_member, members_to_book in allocations
            ]

            # Wait for all bookings to complete
            booking_results = await asyncio.gather(*booking_tasks)

            # Send combined response
            prefix = "[DRY RUN] " if args.dry_run else ""
            response = f"{prefix}Booking Results:\n" + "\n".join(
                f"- {result}" for result in booking_results
            )
            await self.log(c, response)
        except (RuntimeError, ArgumentError) as e:
            await self.log(c, str(e))
