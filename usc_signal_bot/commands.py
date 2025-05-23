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
from usc_signal_bot.usc import AMSTERDAM_TZ, BookableSlot, USCClient, format_slot_date


def resolve_alias(email_or_alias: str, aliases: dict[str, str]) -> str:
    """Resolve an alias to an email address.

    Args:
        email_or_alias: Email address or alias to resolve (case insensitive)
        aliases: Dictionary mapping aliases to email addresses

    Returns:
        str: Resolved email address
    """
    # Convert input to lowercase for case-insensitive matching
    email_or_alias_lower = email_or_alias.lower()

    # Create case-insensitive alias lookup
    aliases_lower = {k.lower(): v for k, v in aliases.items()}

    return aliases_lower.get(email_or_alias_lower, email_or_alias)


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
                return

            if not case_sensitive:
                text = text.lower()
            if not text.startswith(start_word):
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


class AliasesCommand(Command):
    """Command to display all configured aliases."""

    def __init__(self, usc_creds: USCCreds):
        super().__init__()
        self.usc_creds = usc_creds

    def setup(self):
        logging.info("Setting up AliasesCommand")
        return super().setup()

    def describe(self) -> str:
        logging.info("Describing AliasesCommand")
        return super().describe()

    @ignore_unrelated_messages("aliases")
    @notify_error
    async def handle(self, c: Context):
        """Handle the aliases command."""
        logging.info("Handling aliases command")

        if not self.usc_creds.aliases:
            await c.send("No aliases configured.")
            return

        # Format the aliases nicely
        alias_lines = [
            f"- **{alias}** → {email}" for alias, email in sorted(self.usc_creds.aliases.items())
        ]

        response = "Configured aliases:\n" + "\n".join(alias_lines)
        await c.send(response, text_mode="styled")


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
            "courts",
            type=int,
            help="Number of courts to book",
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
            help="Email addresses or aliases of members to book for",
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
        pre_assigned_slot: Optional[BookableSlot] = None,
    ) -> str:
        """Make a booking with a specific member's credentials.

        Args:
            date: Date to book
            members: List of member emails to invite (max 2)
            booking_member: Credentials to use for booking
            dry_run: If True, only simulate the booking without actually making it
            pre_assigned_slot: Optional pre-assigned slot to book

        Returns:
            str: Booking response message
        """
        usc = USCClient()
        try:
            await usc.authenticate(booking_member.username, booking_member.password)

            # Get member info first as we need it for both cases
            booking_member_info = await usc.get_member()

            if pre_assigned_slot:
                slot = pre_assigned_slot
            else:
                slot = await usc.get_matching_slot(date)
                if not slot:
                    raise RuntimeError(f"No available slot found on {date}")

            booking_data = usc.create_booking_data(booking_member_info.id, members, slot=slot)

            if dry_run:
                return f"[DRY RUN] Would book slot {format_slot_date(slot.startDate)} - {format_slot_date(slot.endDate)} with {booking_member.username} for members {', '.join(members)}"

            await usc.book_slot(booking_data)
            return f"Booking successful with {booking_member.username} for members {', '.join(members)}"
        except Exception as e:
            return f"{'[DRY RUN] ' if dry_run else ''}Booking failed with {booking_member.username}: {str(e)}"
        finally:
            await usc.close()

    def _allocate_bookings(
        self, players: List[str], courts: int
    ) -> List[tuple[BookingMember, List[str]]]:
        """Allocate booking members to groups of players.

        This function tries to match booking members with their emails when possible,
        and uses remaining booking members for other players.
        Note: A booking member must always be included in their own booking.

        Args:
            players: List of player emails to book for
            courts: Number of courts user wants us to book

        Returns:
            List of tuples containing (booking_member, list_of_members_to_book_for)
        """
        amount_of_players = len(players)
        authenticated_players = [m for m in self.usc_creds.bookingMembers if m.username in players]
        allocations: List[tuple[BookingMember, List[str]]] = []
        remaining_players = players.copy()
        amount_of_bookings_required = math.ceil(
            amount_of_players / 4
        )  # 1 slot per maximum 4 players

        # Check if the user is a pannenkoek and wants too little courts
        if courts < amount_of_bookings_required:
            raise RuntimeError(
                f"Requested {courts} courts, but at least {amount_of_bookings_required} are needed for {amount_of_players} players"
            )

        amount_of_bookings_to_make = max(amount_of_bookings_required, courts)
        amount_of_authenticated_players = len(authenticated_players)
        players_to_book = [m.username for m in authenticated_players][:amount_of_bookings_to_make]

        if amount_of_authenticated_players < amount_of_bookings_to_make:
            raise RuntimeError(
                f"Not enough authenticated booking members available to book {amount_of_bookings_to_make} squash courts"
            )

        players_per_court = math.ceil(amount_of_players / courts)  # Calculate players per court
        for i in range(amount_of_bookings_to_make):
            booking_member = authenticated_players[i]
            current_group = []
            remaining_players.remove(booking_member.username)
            j = 0
            # For the players_per_court we remove the booking member from the amount of players to book
            while len(remaining_players) > 0 and len(current_group) < players_per_court - 1:
                next_player = remaining_players[j]
                if next_player not in players_to_book:
                    current_group.append(next_player)
                    remaining_players.remove(next_player)
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
            raise RuntimeError(
                f"Error parsing arguments: {str(e)}\n{self.parser.format_help()}"
            ) from e

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

            date = parse(f"{args.date} {args.time}", settings={"TIMEZONE": "Europe/Amsterdam"})
            if not date:
                raise RuntimeError(f"Failed to parse date '{args.date} {args.time}'")

            # Resolve aliases to email addresses
            resolved_members = [resolve_alias(m, self.usc_creds.aliases) for m in args.members]

            # Validate the number of courts for the amount of members
            if args.courts > len(resolved_members):
                raise ValueError("Cannot book more courts than members")

            # Allocate bookings smartly
            allocations = self._allocate_bookings(resolved_members, args.courts)

            # First get all slots and assign them to each booking
            usc = USCClient()
            try:
                # Use first member's credentials to get slots
                first_member = allocations[0][0]
                await usc.authenticate(first_member.username, first_member.password)

                # Get the required number of slots
                available_slots = await usc.get_slots_for_booking(date, len(allocations))

                # Assign slots to each booking
                booking_allocations: List[tuple[BookingMember, List[str], BookableSlot]] = []
                for i, (booking_member, members_to_book) in enumerate(allocations):
                    booking_allocations.append(
                        (booking_member, members_to_book, available_slots[i])
                    )
            finally:
                await usc.close()

            # Make bookings in parallel with pre-assigned slots
            booking_tasks = [
                self._make_booking(date, members_to_book, booking_member, args.dry_run, slot)
                for booking_member, members_to_book, slot in booking_allocations
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
