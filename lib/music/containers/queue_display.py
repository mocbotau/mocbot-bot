import discord
from lavalink import DefaultPlayer

from lib.bot import MOCBOT
from lib.music.MusicService import MusicService
from lib.music.containers.base import BaseMusicContainer
from utils.Music import format_duration


class QueueContainer(BaseMusicContainer):
    """Container to display the music queue with pagination controls."""

    def __init__(self, service: MusicService, player: DefaultPlayer, bot: MOCBOT, page: int = 0, per_page: int = 5):
        super().__init__()

        self.service = service
        self.player = player
        self.bot = bot
        self.page = page
        self.per_page = per_page

        total_tracks = len(player.queue) if player and player.queue else 0
        max_pages = max(1, (total_tracks + per_page - 1) // per_page)
        start_idx = page * per_page
        end_idx = min(start_idx + per_page, total_tracks)

        self._build_header(player, bot)

        if total_tracks == 0:
            self.add_item(discord.ui.TextDisplay("-# Type `/play [SONG]` to add songs to the queue."))
        else:
            self._build_queue_items(start_idx, end_idx)
            self._build_stats(total_tracks, max_pages, page)

        if max_pages > 1:
            self._build_pagination_buttons(page, max_pages)

    def _build_header(self, player: DefaultPlayer, bot: MOCBOT):
        """Build the header section with now playing info."""
        now_playing_text = "N/A"
        requester = ""
        if player and player.current:
            now_playing_text = f"[{player.current.title}]({player.current.uri})"
            requester = f"<@{player.current.requester}>" if player.current.requester else bot.user.mention

        close_button = discord.ui.Button(
            emoji=discord.PartialEmoji(name="close", id=1460940692447559690),
            style=discord.ButtonStyle.secondary,
        )
        close_button.callback = self.handle_close

        self.add_item(discord.ui.Section(
            discord.ui.TextDisplay("**Queue**"),
            accessory=close_button,
        ))

        self.add_item(discord.ui.TextDisplay(f"### **Playing: {now_playing_text}**"))
        self.add_item(discord.ui.TextDisplay('-# Requested by ' + requester if requester else ''))
        self.add_item(discord.ui.Separator())

    def _build_queue_items(self, start_idx: int, end_idx: int):
        """Build the queue track items with delete buttons."""
        for idx in range(start_idx, end_idx):
            track = self.player.queue[idx]
            track_num = idx + 1
            duration = format_duration(track.duration) if not track.stream else "LIVE STREAM"
            requester = f"<@{track.requester}>" if track.requester else self.bot.user.mention
            line_text = f"**{track_num}**. [{track.title}]({track.uri})\n-# {track.author} • {duration} • {requester}"

            delete_button = discord.ui.Button(
                emoji=discord.PartialEmoji(name="delete", id=1460911131433500830),
                style=discord.ButtonStyle.secondary,
                custom_id=f"delete_{idx}",
            )
            delete_button.callback = self._make_delete_callback(idx, track)

            self.add_item(discord.ui.Section(
                discord.ui.TextDisplay(line_text),
                accessory=delete_button,
            ))

    def _build_stats(self, total_tracks: int, max_pages: int, page: int):
        """Build the statistics section."""
        self.add_item(discord.ui.Separator())

        total_duration = sum(t.duration if not t.stream else 0 for t in self.player.queue)
        duration_text = format_duration(total_duration) if total_duration < 86400000 else ">24h"
        stat_string = f"Page {page + 1}/{max_pages} • Total Duration: {duration_text} • {total_tracks} tracks"

        self.add_item(
            discord.ui.TextDisplay(f"-# {stat_string}"),
        )

    def _build_pagination_buttons(self, page: int, max_pages: int):
        """Build pagination control buttons."""
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
        self.add_item(buttons)

    def _make_delete_callback(self, queue_position: int, track):
        """Create a callback function for deleting a specific track."""
        async def delete_callback(interaction: discord.Interaction):
            await self.handle_delete(interaction, queue_position, track)
        return delete_callback

    def _refresh_view(self, page: int) -> discord.ui.LayoutView:
        """Create a new view with updated queue container."""
        new_container = QueueContainer(self.service, self.player, self.bot, page=page, per_page=self.per_page)
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(new_container)
        return view

    async def handle_delete(self, interaction: discord.Interaction, queue_position: int, track):
        """Handle delete button press for a specific track."""
        await self.service.remove(interaction.guild.id, interaction.user.id, queue_position + 1)

        total_tracks = len(self.player.queue) if self.player and self.player.queue else 0
        max_pages = max(1, (total_tracks + self.per_page - 1) // self.per_page) if total_tracks > 0 else 1
        new_page = min(self.page, max_pages - 1) if total_tracks > 0 else 0

        await self._defer_and_update_view(interaction, self._refresh_view(new_page))

    async def handle_first(self, interaction: discord.Interaction):
        """Handle first page button press."""
        await self._defer_and_update_view(interaction, self._refresh_view(0))

    async def handle_prev(self, interaction: discord.Interaction):
        """Handle previous page button press."""
        new_page = max(0, self.page - 1)
        await self._defer_and_update_view(interaction, self._refresh_view(new_page))

    async def handle_next(self, interaction: discord.Interaction):
        """Handle next page button press."""
        total_tracks = len(self.player.queue) if self.player and self.player.queue else 0
        max_pages = max(1, (total_tracks + self.per_page - 1) // self.per_page)
        new_page = min(max_pages - 1, self.page + 1)
        await self._defer_and_update_view(interaction, self._refresh_view(new_page))

    async def handle_last(self, interaction: discord.Interaction):
        """Handle last page button press."""
        total_tracks = len(self.player.queue) if self.player and self.player.queue else 0
        max_pages = max(1, (total_tracks + self.per_page - 1) // self.per_page)
        await self._defer_and_update_view(interaction, self._refresh_view(max_pages - 1))

    async def handle_close(self, interaction: discord.Interaction):
        """Handle close button press."""
        await self._delete_message(interaction)
