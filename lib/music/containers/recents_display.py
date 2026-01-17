import asyncio
from typing import Dict, Any, List
from datetime import datetime
import discord

from lib.bot import MOCBOT
from lib.music.Decorators import message_error_handler
from lib.music.MusicService import MusicService
from lib.music.containers.base import PaginatedContainer
from lib.music.containers.queue_add import QueueAddContainer
from lib.music.views import AutoDeleteLayoutView
from utils.Music import format_duration


class RecentsContainer(PaginatedContainer):
    """Container to display recently played tracks with pagination controls."""

    def __init__(self,
                 service: MusicService,
                 bot: MOCBOT,
                 recents_data: Dict[str, Any],
                 is_server: bool = False,
                 page: int = 0,
                 per_page: int = 5
                 ):
        # Ephemeral if personal recents
        super().__init__(page, per_page, ephemeral=not is_server)

        self.service = service
        self.bot = bot
        self.logger = bot.logger
        self.recents_data = recents_data
        self.is_server = is_server

        track_plays = recents_data.get("trackPlays", [])
        total_tracks = len(track_plays)
        max_pages, start_idx, end_idx = self._calculate_pagination(total_tracks)

        self._build_header(is_server)

        if total_tracks == 0:
            self.add_item(discord.ui.TextDisplay("-# No recent tracks found."))
        else:
            self._build_recent_items(track_plays[start_idx:end_idx], start_idx)
            self._build_stats(total_tracks, max_pages, page)

        self._build_action_row(page,
                               max_pages,
                               track_plays,
                               show_page_buttons=max_pages > 1,
                               show_add_all_button=total_tracks > 0)

    def _build_header(self, is_server: bool):
        """Build the header section."""
        guild_name = self.bot.get_guild(self.recents_data.get("guildId")).name if is_server else ""
        title = f"**`{guild_name}`'s Recently Played Tracks**" if is_server else "**Your Recently Listened Tracks**"

        self.add_item(discord.ui.Section(
            discord.ui.TextDisplay(title),
            accessory=self._build_close_button(),
        ))
        self.add_item(discord.ui.Separator())

    def _build_recent_items(self, track_plays: List[Dict[str, Any]], start_idx: int):
        """Build the recent track items with add buttons."""
        for idx, track_play in enumerate(track_plays):
            track_num = start_idx + idx + 1
            duration = format_duration(track_play.get("DurationMs", 0))

            url = track_play.get("URL", "")

            title = track_play.get("Title", "Unknown Title")
            artist = track_play.get("Artist", "Unknown Artist")
            # show which server the track was played on if not getting server recents
            guild_name = self.bot.get_guild(track_play.get("GuildID")).name if not self.is_server else ""
            relative_time = datetime.fromisoformat(track_play.get("StartedAt")).timestamp()

            line_text = f"**{track_num}**. [{title} - {artist}]({url})\n"
            line_text += f"-# {duration}{f' • `{guild_name}`' if guild_name else ''} • <t:{int(relative_time)}:R>"

            add_button = discord.ui.Button(
                emoji=discord.PartialEmoji(name="plus", id=1461675441097015470),
                style=discord.ButtonStyle.secondary,
                custom_id=f"add_{start_idx + idx}",
            )
            add_button.callback = self._make_add_callback(track_play)

            self.add_item(discord.ui.Section(
                discord.ui.TextDisplay(line_text),
                accessory=add_button,
            ))

    def _build_stats(self, total_tracks: int, max_pages: int, page: int):
        """Build the statistics section."""
        self.add_item(discord.ui.Separator())

        stat_string = f"Page {page + 1}/{max_pages} • {total_tracks} tracks"

        self.add_item(
            discord.ui.TextDisplay(f"-# {stat_string}"),
        )

    def _build_action_row(self,
                          page: int,
                          max_pages: int,
                          track_plays: List[Dict[str, Any]],
                          show_page_buttons: bool = True,
                          show_add_all_button: bool = False):
        """Build action row with add all and/or pagination buttons."""
        buttons = discord.ui.ActionRow()

        if show_add_all_button:
            add_all_button = discord.ui.Button(
                label=f"Add All ({len(track_plays)})",
                emoji=discord.PartialEmoji(name="plus", id=1461675441097015470),
                style=discord.ButtonStyle.blurple,
            )
            add_all_button.callback = self._make_add_all_callback(track_plays)
            buttons.add_item(add_all_button)

        if show_page_buttons:
            pagination_buttons = self._build_pagination_buttons(page, max_pages)
            for item in pagination_buttons.children:
                buttons.add_item(item)

        if show_page_buttons or show_add_all_button:
            self.add_item(buttons)

    def _make_add_callback(self, track_play: Dict[str, Any]):
        """Create a callback function for adding a specific track."""
        async def add_callback(interaction: discord.Interaction):
            await self.handle_add(interaction, track_play)
        return add_callback

    def _make_add_all_callback(self, track_plays: List[Dict[str, Any]]):
        """Create a callback function for adding all tracks."""
        async def add_all_callback(interaction: discord.Interaction):
            await self.handle_add_all(interaction, track_plays)
        return add_all_callback

    def _get_total_items(self) -> int:
        """Get total number of items for pagination."""
        return len(self.recents_data.get("trackPlays", []))

    def _refresh_view(self, page: int) -> discord.ui.LayoutView:
        """Create a new view with updated recents container."""
        new_container = RecentsContainer(
            self.service,
            self.bot,
            self.recents_data,
            self.is_server,
            page=page,
            per_page=self.per_page
        )
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(new_container)
        return view

    @message_error_handler(ephemeral=True, followup=True)
    async def handle_add(self, interaction: discord.Interaction, track_play: Dict[str, Any]):
        """Handle add button press for a specific track."""
        await interaction.response.defer(ephemeral=True)

        url = track_play.get("URL", "")

        result = await self.service.play_track(
            interaction.guild.id,
            interaction.user.id,
            query=url,
            handle_new_player=True
        )

        if result.get("was_playing", False):
            player = self.service.get_player_by_guild(interaction.guild.id)
            container = QueueAddContainer(self.service,
                                          player, result, self.bot, interaction, position=result["queue_position"])
            await self.send_queue_add(interaction, container)

    @message_error_handler(ephemeral=True, followup=True)
    async def handle_add_all(self, interaction: discord.Interaction, track_plays: List[Dict[str, Any]]):
        """Handle add all button press."""
        await interaction.response.defer(ephemeral=True)

        urls = [track_play.get("URL", "") for track_play in track_plays if track_play.get("URL", "")]

        result = await self.service.play_tracks(
            interaction.guild.id,
            interaction.user.id,
            queries=urls,
            handle_new_player=True,
        )
        result["playlist_name"] = "Recent Tracks"  # For display purposes
        await interaction.delete_original_response()

        if result.get("was_playing", False):
            player = self.service.get_player_by_guild(interaction.guild.id)
            container = QueueAddContainer(self.service,
                                          player, result, self.bot, interaction)
            await self.send_queue_add(interaction, container)

    async def send_queue_add(self, interaction: discord.Interaction, container: QueueAddContainer):
        """Send the queue add container as a follow-up message."""
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(container)
        msg = await interaction.followup.send(view=view)
        await asyncio.sleep(AutoDeleteLayoutView.QUEUE_ADD_TIMEOUT)
        await msg.delete()
