"""Signal bot commands."""

import logging
import re
from datetime import datetime
from functools import wraps

from dateparser import parse
from signalbot import Command, Context, triggered

from usc_signal_bot.config import USCCreds
from usc_signal_bot.usc import USCClient, format_slot_date


def notify_error(func):
    @wraps(func)
    async def wrapper_notify_error(self, c: Context):
        try:
            return await func(self, c)
        except Exception as e:
            logging.exception(f"Error in {func.__name__}")
            await c.send(f"Error in {func.__name__}: {e}")

    return wrapper_notify_error


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
        await c.send(f"Pong {datetime.now()}")


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

    @notify_error
    async def handle(self, c: Context):
        if not c.message.text.startswith("timeslots"):
            return
        match = self.message_pattern.match(c.message.text)
        if not match:
            await c.send(
                "Invalid message format. Please use the following format:\ntimeslots <date?>"
            )
            return
        logging.info(f"Received message: {c.message.text}")

        # By default timeslots are released 6 days in advance
        date_str = match.group(1)
        date = parse(date_str or "6 days later")
        if not date:
            await c.send("Invalid date format. Please use the following format:\ntimeslots <date?>")
            return

        usc = USCClient()
        await usc.authenticate(self.usc_creds.username, self.usc_creds.password)
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
        self.message_pattern = re.compile(
            r"^book\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s+(.+@.+\..+){1,3}$", re.IGNORECASE
        )

    def setup(self):
        logging.info("Setting up BookTimeslotCommand")
        return super().setup()

    def describe(self) -> str:
        logging.info("Describing BookTimeslotCommand")
        return super().describe()

    @notify_error
    async def handle(self, c: Context):
        match = self.message_pattern.match(c.message.text)
        if not c.message.text.startswith("book"):
            return
        logging.info(f"Received message: {c.message.text}")
        if not match:
            await c.send(
                "Invalid message format. Please use the following format:\nbook <date> <time> <email1> <email2?> <email3?>"
            )
            return

        date_str = match.group(1)
        time_str = match.group(2)
        members = match.group(3).split(" ")
        date = parse(f"{date_str} {time_str}")
        if not date:
            raise RuntimeError(f"Failed to parse date '{date_str} {time_str}'")

        usc = USCClient()
        await usc.authenticate(self.usc_creds.username, self.usc_creds.password)
        slot = await usc.get_matching_slot(date)
        if not slot:
            raise RuntimeError(f"No available slot found on {date}")

        booking_member = await usc.get_member()
        booking_data = usc.create_booking_data(booking_member.id, members, slot=slot)

        response = await usc.book_slot(booking_data)
        await c.send(f"Booking response: {response}", text_mode="styled")
        await usc.close()
