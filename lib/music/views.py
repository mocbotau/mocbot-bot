import discord
from discord import Interaction
from discord.ui import LayoutView


class QueueLayoutView(LayoutView):
    """Custom LayoutView for queue that deletes the message on timeout."""

    DEFAULT_TIMEOUT = 45.0

    def __init__(self, interaction: Interaction, timeout: float = DEFAULT_TIMEOUT):
        super().__init__(timeout=timeout)
        self.interaction = interaction

    async def on_timeout(self) -> None:
        """Delete the message when the view times out."""
        try:
            await self.interaction.delete_original_response()
        except (discord.NotFound, discord.HTTPException):
            pass  # Message already deleted or not found
