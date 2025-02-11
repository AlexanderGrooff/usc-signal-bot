"""Main entry point for the USC Signal Bot."""

import logging
import sys

from usc_signal_bot.bot import main

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)


if __name__ == "__main__":
    main() 
