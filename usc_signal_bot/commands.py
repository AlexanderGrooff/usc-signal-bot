"""Signal bot commands."""

import logging
from datetime import datetime

from signalbot import Command, Context, triggered

from usc_signal_bot.config import USCCreds
from usc_signal_bot.usc import USCClient


class PingCommand(Command):
    """Simple ping command that responds with the current time."""

    def setup(self):
        logging.info("Setting up PingCommand")
        return super().setup()

    def describe(self) -> str:
        logging.info("Describing PingCommand")
        return super().describe()

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

    @triggered("timeslots")
    async def handle(self, c: Context):
        logging.info(f"Received message: {c.message.text}")
        usc = USCClient()
        try:
            await usc.authenticate(self.usc_creds.username, self.usc_creds.password)
            timeslots = await usc.get_slots(datetime.now())

            # Format the response
            available_slots = [
                f"- {slot.startDate} - {slot.endDate}"
                for slot in timeslots.data
                if slot.isAvailable
            ]

            if available_slots:
                response = "Available slots:\n" + "\n".join(available_slots)
            else:
                response = "No available slots found"

            await c.send(response)
        except Exception as e:
            logging.error(f"Error getting timeslots: {e}")
            await c.send(f"Error getting timeslots: {e}")
        finally:
            await usc.close()
