from typing import Callable
import functools
import discord

from lib.music.Exceptions import UserError, InternalError
from utils.Music import send_message


def message_error_handler(ephemeral=True, followup=False):
    """A decorator factory to handle UserError and InternalError exceptions in command methods."""

    def decorator(f: Callable):
        @functools.wraps(f)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            try:
                return await f(self, interaction, *args, **kwargs)
            except UserError as e:
                await send_message(self.bot, interaction, str(e), ephemeral=ephemeral, followup=followup)
            except InternalError as e:
                self.logger.error("InternalError: {%s}", e)
                await send_message(
                    self.bot,
                    interaction,
                    "An internal error occurred while processing your request. The incident has been logged.",
                    ephemeral=ephemeral,
                    followup=followup,
                )
            except Exception as e:
                self.logger.error("Unexpected error in %s: %s", f.__name__, e, exc_info=True)
                await send_message(
                    self.bot,
                    interaction,
                    "An unexpected error occurred while processing your request. The incident has been logged.",
                    ephemeral=ephemeral,
                    followup=followup,
                )
                raise

        return wrapper

    return decorator


def event_handler(event_name: str):
    """Decorator to mark methods as event handlers."""

    def wrapper(func):
        if not hasattr(func, "event_names"):
            setattr(func, "event_names", [])
        func.event_names.append(event_name)
        return func

    return wrapper
