import logging
import os

import yaml
from signalbot import SignalBot

from usc_signal_bot.commands import GetTimeslotsCommand, PingCommand
from usc_signal_bot.config import Config


def main():
    """Main entry point for the bot."""
    # Load main configuration
    config_file = os.getenv("CONFIG_FILE", "/config/config.yaml")
    logging.info(f"Loading config from {config_file}")
    with open(config_file) as f:
        config = yaml.safe_load(f)
    assert isinstance(config, dict)  # Type assertion for mypy

    # Load command configuration
    config = Config(**config)

    # Create and start the bot with config from file
    logging.info(f"Starting bot with config: {config.bot}")
    logging.info(f"Commands config: {config.commands}")
    bot = SignalBot(config.bot.model_dump())

    # Register commands with their specific configurations
    for cmd in config.commands:
        logging.info(f"Registering command: {cmd.name}")
        if cmd.name == "ping":
            bot.register(PingCommand(), contacts=cmd.contacts, groups=cmd.groups)
        elif cmd.name == "timeslots":
            bot.register(GetTimeslotsCommand(config.usc), contacts=cmd.contacts, groups=cmd.groups)

    bot.start()
