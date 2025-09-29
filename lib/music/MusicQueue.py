from functools import reduce
from utils.Pagination import BasePaginationMenu, BasePaginationSource
from utils.Music import format_duration


class QueueMenu(BasePaginationMenu):
    """Queue pagination menu that extends the base pagination functionality"""

    async def send_initial_message(self):
        """Override to use response.send_message for queue"""
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        await self.interaction.response.send_message(**kwargs)
        return await self.interaction.original_response()


class QueuePagination(BasePaginationSource):
    """Queue pagination source that formats queue pages"""

    def __init__(self, player, interaction, MusicCls):
        super().__init__(player.queue if player is not None else [], per_page=10)
        self.interaction = interaction
        self.Music = MusicCls
        self.player = player
        self.emptyQueueMsg = "Type `/play [SONG]` to add songs to the queue."

    async def format_page(self, menu, page):
        """Format a queue page with proper embed styling"""
        offset = (menu.current_page * self.per_page) + 1
        now_playing = (
            f"[{self.player.current.title}]({self.player.current.uri})"
            if self.player is not None and self.player.current is not None
            else "N/A"
        )
        queueContent = "{}\n\n**CURRENT QUEUE:**\n{}".format(
            f"> NOW PLAYING: {now_playing}",
            (
                "\n".join(
                    [
                        f"{index}. [{track.title}]({track.uri}) - "
                        f'{format_duration(track.duration) if not track.stream else "LIVE STREAM"}'
                        for index, track in enumerate(page, start=offset)
                    ]
                )
                if page
                else self.emptyQueueMsg
            ),
        )
        embed = self.interaction.client.create_embed("MOCBOT MUSIC", queueContent, None)

        if page:
            duration = reduce(
                lambda a, b: a + b,
                [song.duration if not song.stream else 0 for song in self.player.queue],
            )
            embed.add_field(
                name="**Total Duration**",
                value=(format_duration(duration) if (duration < 86400000) else ">24h"),
                inline=True,
            )
            embed.add_field(
                name="**Total Tracks**",
                value=len(self.player.queue),
                inline=True,
            )

        embed.set_footer(
            text=f"Page {menu.current_page + 1}/{self.get_max_pages() or 1} | Requested by {self.interaction.user}"
        )
        return embed
