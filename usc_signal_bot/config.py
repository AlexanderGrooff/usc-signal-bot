"""Configuration classes for the USC Signal Bot."""

from typing import List, Union

from pydantic import BaseModel


class SignalConfig(BaseModel):
    """Configuration for the Signal API."""

    phone_number: str
    signal_service: str


class CommandConfig(BaseModel):
    """Configuration for a single command."""

    name: str
    contacts: Union[List[str], bool] = False
    groups: Union[List[str], bool] = False


class USCCreds(BaseModel):
    """Credentials for the USC API."""

    username: str
    password: str


class Config(BaseModel):
    """Main configuration for the bot."""

    bot: SignalConfig
    usc: USCCreds
    commands: List[CommandConfig]
