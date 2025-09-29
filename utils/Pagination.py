from discord.ext import menus
from discord.ui import Button, View
import discord


class BasePaginationSource(menus.ListPageSource):
    """Base pagination source class that can be extended for specific use cases"""

    def __init__(self, entries, per_page=10):
        super().__init__(entries, per_page=per_page)

    async def format_page(self, menu, entries):
        """Override this method in subclasses to format the page content"""
        raise NotImplementedError("Subclasses must implement format_page method")


class BasePaginationMenu(View, menus.MenuPages):
    """Base pagination menu class that consolidates common pagination logic"""

    def __init__(self, source, interaction, timeout=20):
        super().__init__(timeout=timeout)
        self._source = source
        self.current_page = 0
        self.ctx = None
        self.message = None
        self.interaction = interaction
        self._create_buttons()

    async def on_timeout(self) -> None:
        """Handle timeout by deleting the original response"""
        try:
            await self.interaction.delete_original_response()
        except discord.NotFound:
            pass  # Message already deleted

    async def start(self, ctx, *, channel=None, wait=False):
        """Start the pagination menu"""
        await self._source._prepare_once()
        self.ctx = ctx
        self.message = await self.send_initial_message()

    async def send_initial_message(self):
        """Send the initial message with the first page"""
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)

        if self.interaction.response.is_done():
            await self.interaction.followup.send(**kwargs)
            return await self.interaction.original_response()
        else:
            await self.interaction.response.send_message(**kwargs)
            return await self.interaction.original_response()

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction):
        """Show a page after checking if it's valid"""
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                await self.show_page(page_number, interaction)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number, interaction)
        except IndexError:
            pass  # Ignore invalid page numbers

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        """Show a specific page"""
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)

        self._update_button_states()

        await interaction.response.edit_message(**kwargs)

    async def _get_kwargs_from_page(self, page):
        """Get kwargs from page and include the view"""
        value = await super()._get_kwargs_from_page(page)
        if "view" not in value:
            value.update({"view": self})
        return value

    async def interaction_check(self, interaction: discord.Interaction):
        """Only allow the original author to use the interactions"""
        return interaction.user == self.ctx.author

    def _create_buttons(self):
        """Create pagination buttons with smart visibility"""
        max_pages = self._source.get_max_pages()

        if max_pages is None or max_pages <= 1:
            return

        self.first_button = Button(label="First Page", style=discord.ButtonStyle.secondary, disabled=True)
        self.first_button.callback = self._first_page_callback

        self.previous_button = Button(label="Previous Page", style=discord.ButtonStyle.secondary, disabled=True)
        self.previous_button.callback = self._previous_page_callback

        self.next_button = Button(label="Next Page", style=discord.ButtonStyle.secondary, disabled=(max_pages <= 1))
        self.next_button.callback = self._next_page_callback

        self.last_button = Button(label="Last Page", style=discord.ButtonStyle.secondary, disabled=(max_pages <= 1))
        self.last_button.callback = self._last_page_callback

        self.close_button = Button(label="Close", style=discord.ButtonStyle.danger)
        self.close_button.callback = self._close_callback

        self.add_item(self.first_button)
        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.add_item(self.last_button)
        self.add_item(self.close_button)

    def _update_button_states(self):
        """Update button enabled/disabled states based on current page"""
        max_pages = self._source.get_max_pages()

        if max_pages is None or max_pages <= 1:
            return

        is_first_page = self.current_page == 0
        if hasattr(self, "first_button"):
            self.first_button.disabled = is_first_page
        if hasattr(self, "previous_button"):
            self.previous_button.disabled = is_first_page

        is_last_page = self.current_page >= max_pages - 1
        if hasattr(self, "next_button"):
            self.next_button.disabled = is_last_page
        if hasattr(self, "last_button"):
            self.last_button.disabled = is_last_page

    async def _first_page_callback(self, interaction):
        """Go to first page"""
        await self.show_page(0, interaction)

    async def _previous_page_callback(self, interaction):
        """Go to previous page"""
        await self.show_checked_page(self.current_page - 1, interaction)

    async def _next_page_callback(self, interaction):
        """Go to next page"""
        await self.show_checked_page(self.current_page + 1, interaction)

    async def _last_page_callback(self, interaction):
        """Go to last page"""
        max_pages = self._source.get_max_pages()
        if max_pages and max_pages > 0:
            await self.show_page(max_pages - 1, interaction)

    async def _close_callback(self, interaction):
        """Close the pagination menu"""
        await interaction.response.defer()
        await self.interaction.delete_original_response()
        self.stop()
