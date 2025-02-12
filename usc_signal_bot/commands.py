"""Signal bot commands."""

import logging
from datetime import datetime
from functools import wraps

from signalbot import Command, Context, triggered

from usc_signal_bot.config import USCCreds
from usc_signal_bot.usc import USCClient, format_slot_date


def notify_error(func):
    @wraps(func)
    async def wrapper_notify_error(self, c: Context):
        try:
            return await func(self, c)
        except Exception as e:
            logging.error(f"Error in {func.__name__}: {e}")
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

    def setup(self):
        logging.info("Setting up GetTimeslotsCommand")
        return super().setup()

    def describe(self) -> str:
        logging.info("Describing GetTimeslotsCommand")
        return super().describe()

    @notify_error
    @triggered("timeslots")
    async def handle(self, c: Context):
        logging.info(f"Received message: {c.message.text}")
        usc = USCClient()

        await usc.authenticate(self.usc_creds.username, self.usc_creds.password)
        timeslots = await usc.get_slots("5 days later")

        # Format the response
        grouped_slots = usc.format_slots(timeslots.data)
        available_slots = [
            f"- {format_slot_date(start_date)} - {format_slot_date(slots[0].endDate)} - **{len(slots)} slots available**"
            for start_date, slots in grouped_slots.items()
        ]

        if available_slots:
            response = "Available slots:\n" + "\n".join(available_slots)
        else:
            response = "No available slots found"

        await c.send(response, text_mode="styled")
        await usc.close()
