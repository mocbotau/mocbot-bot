from utils.Pagination import BasePaginationMenu, BasePaginationSource


class LyricsMenu(BasePaginationMenu):
    """Lyrics pagination menu that extends the base pagination functionality"""

    async def send_initial_message(self):
        """Override to use followup for lyrics since interaction might already be responded to"""
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        await self.interaction.followup.send(**kwargs)
        return await self.interaction.original_response()


class LyricsPagination(BasePaginationSource):
    """Lyrics pagination source that formats lyrics pages"""

    def __init__(self, interaction, lyrics, song, artist):
        super().__init__(lyrics, per_page=1)
        self.interaction = interaction
        self.song = song
        self.artist = artist

    async def format_page(self, menu, page):
        """Format a lyrics page with proper embed styling"""
        embed = self.interaction.client.create_embed(f"{self.song} by {self.artist}", page, None)
        embed.set_footer(
            text=f"Page {menu.current_page + 1}/{self.get_max_pages() or 1} | Requested by {self.interaction.user}"
        )
        return embed
