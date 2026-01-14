from typing import TYPE_CHECKING
import discord

if TYPE_CHECKING:
    from lib.bot import MOCBOT
    from lib.music.MusicService import MusicService


class BaseMusicContainer(discord.ui.Container):
    """Base class for all music containers with common styling and utilities."""

    ACCENT_COLOR = 0xDC3145

    service: "MusicService"
    bot: "MOCBOT"

    def __init__(self):
        super().__init__()
        self.accent_color = self.ACCENT_COLOR

    async def _defer_and_update_view(self, interaction: discord.Interaction, new_view: discord.ui.View):
        """Helper to defer interaction and update message with new view."""
        await interaction.response.defer()
        await interaction.message.edit(view=new_view, allowed_mentions=discord.AllowedMentions.none())

    async def _delete_message(self, interaction: discord.Interaction):
        """Helper to defer and delete the message."""
        await interaction.response.defer()
        await interaction.delete_original_response()
