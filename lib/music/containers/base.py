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


class PaginatedContainer(BaseMusicContainer):
    """Base class for paginated music containers with common pagination logic."""

    def __init__(self, page: int = 0, per_page: int = 5):
        super().__init__()
        self.page = page
        self.per_page = per_page
        self.first_button = None
        self.prev_button = None
        self.next_button = None
        self.last_button = None

    def _calculate_pagination(self, total_items: int) -> tuple[int, int, int]:
        """Calculate pagination values. Returns (max_pages, start_idx, end_idx)."""
        max_pages = max(1, (total_items + self.per_page - 1) // self.per_page)
        start_idx = self.page * self.per_page
        end_idx = min(start_idx + self.per_page, total_items)
        return max_pages, start_idx, end_idx

    def _build_pagination_buttons(self, page: int, max_pages: int) -> discord.ui.ActionRow:
        """Build pagination control buttons and return the ActionRow."""
        buttons = discord.ui.ActionRow()

        self.first_button = discord.ui.Button(
            emoji=discord.PartialEmoji(name="first_page", id=1460939335502401689),
            style=discord.ButtonStyle.secondary,
            disabled=(page == 0),
        )
        self.first_button.callback = self.handle_first

        self.prev_button = discord.ui.Button(
            emoji=discord.PartialEmoji(name="prev_page", id=1460940068901355522),
            style=discord.ButtonStyle.secondary,
            disabled=(page == 0),
        )
        self.prev_button.callback = self.handle_prev

        self.next_button = discord.ui.Button(
            emoji=discord.PartialEmoji(name="next_page", id=1460940082629578774),
            style=discord.ButtonStyle.secondary,
            disabled=(page >= max_pages - 1),
        )
        self.next_button.callback = self.handle_next

        self.last_button = discord.ui.Button(
            emoji=discord.PartialEmoji(name="last_page", id=1460939333098934476),
            style=discord.ButtonStyle.secondary,
            disabled=(page >= max_pages - 1),
        )
        self.last_button.callback = self.handle_last

        buttons.add_item(self.first_button)
        buttons.add_item(self.prev_button)
        buttons.add_item(self.next_button)
        buttons.add_item(self.last_button)
        return buttons

    def _build_close_button(self) -> discord.ui.Button:
        """Build and return a close button."""
        close_button = discord.ui.Button(
            emoji=discord.PartialEmoji(name="close", id=1460940692447559690),
            style=discord.ButtonStyle.secondary,
        )
        close_button.callback = self.handle_close
        return close_button

    async def handle_first(self, interaction: discord.Interaction):
        """Handle first page button press."""
        await self._defer_and_update_view(interaction, self._refresh_view(0))

    async def handle_prev(self, interaction: discord.Interaction):
        """Handle previous page button press."""
        new_page = max(0, self.page - 1)
        await self._defer_and_update_view(interaction, self._refresh_view(new_page))

    async def handle_next(self, interaction: discord.Interaction):
        """Handle next page button press."""
        total_items = self._get_total_items()
        max_pages = max(1, (total_items + self.per_page - 1) // self.per_page)
        new_page = min(max_pages - 1, self.page + 1)
        await self._defer_and_update_view(interaction, self._refresh_view(new_page))

    async def handle_last(self, interaction: discord.Interaction):
        """Handle last page button press."""
        total_items = self._get_total_items()
        max_pages = max(1, (total_items + self.per_page - 1) // self.per_page)
        await self._defer_and_update_view(interaction, self._refresh_view(max_pages - 1))

    async def handle_close(self, interaction: discord.Interaction):
        """Handle close button press."""
        await self._delete_message(interaction)

    def _refresh_view(self, _page: int) -> discord.ui.LayoutView:
        """Create a new view with updated container. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement _refresh_view")

    def _get_total_items(self) -> int:
        """Get total number of items for pagination. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement _get_total_items")
