import discord
from discord import Interaction
from discord.ui import LayoutView


class AutoDeleteLayoutView(LayoutView):
    """Custom LayoutView that auto-deletes the message after timeout"""

    QUEUE_ADD_TIMEOUT = 10.0
    QUEUE_DISPLAY_TIMEOUT = 45.0
    RECENTS_DISPLAY_TIMEOUT = 45.0

    def __init__(self, interaction: Interaction, timeout: float | None = None):
        """Initialize the view with auto-delete behaviour"""
        super().__init__(timeout=timeout)
        self.interaction = interaction

    async def on_timeout(self) -> None:
        """Delete the message when the view times out."""
        try:
            await self.interaction.delete_original_response()
        except (discord.NotFound, discord.HTTPException):
            pass  # Message already deleted or not found


def build_view(container: discord.ui.Container, interaction: Interaction = None, timeout: float = None) -> LayoutView:
    """Build a view with the given container"""
    if timeout is not None and interaction is not None:
        view = AutoDeleteLayoutView(interaction, timeout=timeout)
    else:
        view = LayoutView(timeout=timeout)

    view.add_item(container)
    return view
