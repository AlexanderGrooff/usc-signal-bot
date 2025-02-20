import logging
import os

import yaml
from signalbot import SignalBot

from usc_signal_bot.commands import (
    AliasesCommand,
    BookTimeslotCommand,
    GetTimeslotsCommand,
    PingCommand,
)
from usc_signal_bot.config import Config


def load_config() -> Config:
    """Load the config from the config file."""
    config_file = os.getenv("CONFIG_FILE", "/config/config.yaml")
    logging.info(f"Loading config from {config_file}")
    with open(config_file) as f:
        config = yaml.safe_load(f)
    assert isinstance(config, dict)  # Type assertion for mypy
    return Config(**config)


def main():
    """Main entry point for the bot."""
    # Load main configuration
    config = load_config()

    # Create and start the bot with config from file
    logging.info(f"Starting bot with config: {config.bot}")
    logging.info(f"Commands config: {config.commands}")
    bot = SignalBot(config.bot.model_dump())

    # Register commands with their specific configurations
    for cmd in config.commands:
        logging.info(f"Registering command: {cmd.name}")
        match cmd.name:
            case "ping":
                bot.register(PingCommand(), contacts=cmd.contacts, groups=cmd.groups)
            case "timeslots":
                bot.register(
                    GetTimeslotsCommand(config.usc), contacts=cmd.contacts, groups=cmd.groups
                )
            case "book":
                bot.register(
                    BookTimeslotCommand(config.usc), contacts=cmd.contacts, groups=cmd.groups
                )
            case "aliases":
                bot.register(AliasesCommand(config.usc), contacts=cmd.contacts, groups=cmd.groups)

    bot.start()
