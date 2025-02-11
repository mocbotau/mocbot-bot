import logging
import os
import yaml


class Config:
    CONFIG_FILENAME = os.environ["CONFIG_FILE"]
    LOGGER = logging.getLogger(__name__)

    CONFIG = {}

    @staticmethod
    def fetch():
        if not Config.CONFIG:
            try:
                with open(Config.CONFIG_FILENAME, "r", encoding="utf-8") as f:
                    Config.CONFIG = yaml.safe_load(f)
            except IOError:
                Config.LOGGER.error("Could not find a config file. Please see the README.md for setup instructions")

        return Config.CONFIG
