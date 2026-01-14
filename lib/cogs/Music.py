import re
import asyncio
import typing
import logging
from typing import Literal, TYPE_CHECKING, Callable

import requests
from requests import HTTPError
import discord
from discord import PartialMessage, Guild, TextChannel, Interaction, VoiceState, Member
from discord.ext import commands
from discord.ui import View, LayoutView
from discord import app_commands
from lavalink import DefaultPlayer

from utils.APIHandler import API
from utils.Music import convert_to_ms, format_duration, format_lyrics_for_display
from lib.music.MusicLyrics import LyricsMenu, LyricsPagination
from lib.music.Filters import filter_manager
from lib.music.Types import AutoplayMode, PlayerStopped

from lib.music.Decorators import message_error_handler, event_handler
from lib.music.EmbedFactory import MusicEmbedFactory
from lib.music.containers import NowPlayingContainer, QueueAddContainer, QueueContainer
from lib.music.views import QueueLayoutView

if TYPE_CHECKING:
    from lib.bot import MOCBOT


class Music(commands.Cog):
    MESSAGE_ALIVE_TIME = 10  # seconds

    def __init__(self, bot: "MOCBOT"):
        self.bot = bot
        self.embeds = MusicEmbedFactory(bot)
        self.logger = logging.getLogger(__name__)
        self.players = {}
        self._registered_handlers: list[tuple[str, Callable]] = []
        self.service = bot.music_service

    async def cog_load(self):
        for attr_name in dir(self):
            method = getattr(self, attr_name)
            if callable(method) and hasattr(method, "event_names"):
                event_names = getattr(method, "event_names")
                for event_name in event_names:
                    self.service.emitter.on(event_name, method)
                    self._registered_handlers.append((event_name, method))
        self.logger.info("[COG] Loaded %s", self.__class__.__name__)

    async def cog_unload(self):
        """Cog unload handler. This removes any event hooks that were registered."""
        for event_name, method in self._registered_handlers:
            self.service.emitter.off(event_name, method)
        self._registered_handlers.clear()
        self.logger.info("[COG] Unloaded %s", self.__class__.__name__)

    async def send_message(self, interaction: Interaction, msg: str, ephemeral=False, followup=False):
        """Helper function to send messages to the user."""
        if followup:
            await interaction.followup.send(embed=self.bot.create_embed("MOCBOT MUSIC", msg), ephemeral=ephemeral)
        else:
            await interaction.response.send_message(
                embed=self.bot.create_embed("MOCBOT MUSIC", msg), ephemeral=ephemeral
            )

        if not ephemeral:
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)

    async def delay_delete(self, interaction: Interaction, time: float):
        """Helper function to delete a message after a delay."""
        await asyncio.sleep(time)
        try:
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            pass  # Message already deleted

    @event_handler("track_started")
    async def handle_track_start(self, player: DefaultPlayer):
        """Handle the start of a track for a guild"""
        guild_id = player.guild_id
        guild = self.bot.get_guild(guild_id)

        if guild_id not in self.players:
            await self.handle_new_player(player)
            return

        await self.send_new_now_playing(guild, player)

    @event_handler("now_playing_update")
    @event_handler("queue_update")
    async def handle_now_playing_update(self, player: DefaultPlayer):
        """Handle updating the now playing message for a guild"""
        guild = self.bot.get_guild(player.guild_id)
        if player.guild_id not in self.players:
            return

        asyncio.create_task(self.update_now_playing(guild, player))

    @event_handler("player_stopped")
    async def disconnect_bot(self, data: PlayerStopped):
        """Disconnect the bot from voice and clean up any now playing messages."""
        player = data["player"]
        guild_id = player.guild_id
        guild = self.bot.get_guild(guild_id)

        disconnect = data.get("disconnect", False)
        if disconnect:
            await guild.voice_client.disconnect(force=True)

        channel = guild.get_channel(self.players[guild_id]["CHANNEL"])
        message = self.retrieve_now_playing(channel, guild)
        if message is not None:
            await message.delete()

        del self.players[guild_id]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState):
        """Handle voice state updates"""
        # If there are no members left in the voice channel, disconnect the bot
        if member.id != self.bot.user.id:
            if after.channel is None and before.channel is not None and len(before.channel.members) == 1:
                # prefer to emit event so all listeners get notified
                await self.service.emitter.emit(
                    "player_stopped",
                    {"player": self.service.get_player_by_guild(before.channel.guild.id), "disconnect": True},
                )
            return

        # Handle bot moving to new channel gracefully
        if before.channel and after.channel and before.channel != after.channel:
            guild_id = member.guild.id
            player = self.service.get_player_by_guild(guild_id)

            if player and player.is_connected:
                if hasattr(member.guild.voice_client, "channel"):
                    member.guild.voice_client.channel = after.channel

            self.service.emitter.emit("player_state_update", player)

    async def update_now_playing(self, guild: Guild, player: DefaultPlayer):
        """Update the now playing message for a guild"""
        channel = guild.get_channel(self.players[guild.id]["CHANNEL"])
        message = await channel.fetch_message(self.players[guild.id]["MESSAGE_ID"])
        # For some reason edit causes a ping despite the global disable, explicitly set allowed_mentions to none
        await message.edit(
            view=self.build_view(NowPlayingContainer(self.service, player, player.current, self.bot)),
            allowed_mentions=discord.AllowedMentions.none())

    async def send_new_now_playing(self, guild: Guild, player: DefaultPlayer):
        """Send a new now playing message for a guild"""
        channel = guild.get_channel(self.players[guild.id]["CHANNEL"])
        message = self.retrieve_now_playing(channel, guild)
        if message is not None:
            await message.delete()
        message = await channel.send(
            view=self.build_view(NowPlayingContainer(self.service, player, player.current, self.bot)))
        self.players[guild.id] = {"CHANNEL": channel.id, "MESSAGE_ID": message.id, "FIRST": False}

    def retrieve_now_playing(self, channel: TextChannel, guild: Guild) -> PartialMessage | None:
        """Retrieve the now playing message for a guild, returning a partial message to save on API calls"""
        try:
            message = channel.get_partial_message(self.players[guild.id]["MESSAGE_ID"])
        except discord.errors.NotFound:
            return None

        return message

    def get_channel_to_send(self, guild: Guild):
        """Get the channel to send the now playing message to"""
        settings = None
        try:
            settings = API.get(f"/settings/{guild.id}")
        except HTTPError:
            pass  # Ignore errors, we'll find a channel otherwise

        channel = None
        if settings is not None and settings.get("MusicChannel") is not None:
            channel = self.bot.get_channel(int(settings.get("MusicChannel")))

        if channel is None:
            text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages]
            if not text_channels:
                self.logger.warning(
                    "[MUSIC] [{%s} // {%s}] No text channel to send now playing message to.", guild.name, guild.id
                )
                return None

            channel = next((c for c in text_channels if "music" in c.name), text_channels[0])

        return channel

    async def handle_new_player(self, player: DefaultPlayer, interaction: Interaction = None):
        """Handle setting up a new player for a guild"""
        if interaction is None:
            handle_new_player = player.fetch("handle_new_player", True)
            player.store("handle_new_player", True)
            if not handle_new_player:
                return

            channel = self.get_channel_to_send(self.bot.get_guild(player.guild_id))
            if channel is None:
                return

            await channel.send(
                view=self.build_view(NowPlayingContainer(self.service, player, player.current, self.bot)))
            self.players[player.guild_id] = {"CHANNEL": channel.id, "MESSAGE_ID": channel.last_message_id}
            return

        await interaction.followup.send(
            view=self.build_view(NowPlayingContainer(self.service, player, player.current, self.bot)))
        message = await interaction.original_response()
        self.players[interaction.guild.id] = {"CHANNEL": interaction.channel.id, "MESSAGE_ID": message.id}

    def build_view(self, container: discord.ui.Container, timeout=None) -> LayoutView:
        """Build the now playing view for a player"""
        view = discord.ui.LayoutView(timeout=timeout)
        view.add_item(
            container
        )
        return view

    @app_commands.command(
        name="play", description="Search and play media from YouTube, Spotify, SoundCloud, Apple Music etc."
    )
    @app_commands.describe(query="A search query or URL to the media.")
    @message_error_handler(ephemeral=False, followup=True)
    async def play(self, interaction: Interaction, query: str):
        """Searches and plays a song from a given query."""
        await interaction.response.defer(thinking=True)

        result = await self.service.play_track(
            guild_id=interaction.guild.id, user_id=interaction.user.id, query=query, handle_new_player=False
        )

        player = self.service.get_player_by_guild(interaction.guild.id)

        if result["was_playing"]:
            view = QueueAddContainer(self.service,
                                     player, result, self.bot, interaction, position=result["queue_position"])
            await interaction.followup.send(view=view)
            await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)
        else:
            await self.handle_new_player(player, interaction=interaction)
            if result.get("playlist_name") is not None:
                playlist_string = f"**[{result['playlist_name']}]({result['playlist_url']})**"
                await self.send_message(
                    interaction,
                    f"Queued playlist {playlist_string} with **{result['playlist_length']}** tracks.",
                    followup=True,
                )

    @app_commands.command(
        name="skip",
        description="Skips the current media to the next one in queue.",
    )
    @app_commands.describe(position="The queue item number to skip to.")
    @message_error_handler()
    async def skip(self, interaction: Interaction, position: typing.Optional[int] = 1):
        """Skip the current track or a specific track in the queue."""
        result = await self.service.skip(interaction.guild.id, interaction.user.id, position)
        await self.send_message(
            interaction,
            f"Successfully skipped the track [{result['title']}]({result['uri']}).",
        )

    @app_commands.command(name="previous", description="Plays the previous track in the queue.")
    @message_error_handler()
    async def previous(self, interaction: Interaction):
        """Plays the previous track in the queue."""
        last_track = await self.service.previous(interaction.guild.id, interaction.user.id)
        await self.send_message(
            interaction,
            f"Successfully playing the previous track [{last_track['title']}]({last_track['uri']}).",
        )

    @app_commands.command(name="queue", description="Retrieve the music queue.")
    async def queue(self, interaction: Interaction):
        """Displays the current music queue."""
        player = self.service.get_player_by_guild(interaction.guild.id)
        container = QueueContainer(self.service, player, self.bot)
        view = QueueLayoutView(interaction)
        view.add_item(container)
        await interaction.response.send_message(view=view)

    @app_commands.command(name="seek", description="Seeks the current song.")
    @app_commands.describe(time="The time to seek to. Supported formats: 10 | 1:10 | 1:10:10")
    @message_error_handler()
    async def seek(self, interaction: Interaction, time: str):
        """Seek to a specific time in the current track."""
        if (time := convert_to_ms(time)) is None:
            return await self.send_message(
                interaction,
                "Please provide the time to seek in a suitable format.\nExamples: `10 | 1:10 | 1:10:10`",
                ephemeral=True,
            )

        new_position = await self.service.seek(interaction.guild.id, interaction.user.id, time)
        await self.send_message(interaction, f"Seeked to `{format_duration(new_position)}`.")

    @app_commands.command(name="loop", description="Loop the current media or queue.")
    @message_error_handler()
    async def loop(self, interaction: Interaction, mode: Literal["Off", "Song", "Queue"]):
        """Set the loop mode for the current player."""
        result = await self.service.loop(interaction.guild.id, interaction.user.id, mode)
        msg = f"Loop mode set to: `{mode}`."
        if result["autoplay_on"] and mode != "Off":
            msg += "\nNote: Autoplay is still enabled, but the set loop mode takes precedence."

        await self.send_message(interaction, msg)

    @app_commands.command(name="disconnect", description="Disconnects the bot from voice.")
    @message_error_handler()
    async def disconnect(self, interaction: Interaction):
        """Disconnects the player from the voice channel and clears its queue."""
        await self.service.stop(interaction.guild.id, interaction.user.id, disconnect=True)
        await self.send_message(interaction, "MOCBOT has been disconnected and the queue has been cleared.")

    @app_commands.command(name="stop", description="Stops any media that is playing.")
    @message_error_handler()
    async def stop(self, interaction: Interaction):
        """Stops the player."""
        await self.service.stop(interaction.guild.id, interaction.user.id, disconnect=False)
        await self.send_message(interaction, "Playback has been stopped and the queue has been cleared.")

    @app_commands.command(name="filters", description="Toggles audio filters")
    @message_error_handler(ephemeral=False, followup=False)
    async def filters(self, interaction: Interaction):
        """Displays a dropdown menu to toggle audio filters."""
        player = self.service.get_player_by_guild(interaction.guild.id)
        if player is None or (not player.is_playing and not player.is_paused):
            return await self.send_message(interaction, "This command can only be used while music is playing.", True)
        view = filter_manager.create_dropdown_view(self.service, interaction)
        await interaction.response.send_message(view=view)

    @app_commands.command(name="pause", description="Pauses the music")
    @message_error_handler()
    async def pause(self, interaction: Interaction):
        """Pauses the current track."""
        await self.service.pause(interaction.guild.id, interaction.user.id)
        await self.send_message(interaction, "Media has been paused.")

    @app_commands.command(name="resume", description="Resumes the music")
    @message_error_handler()
    async def resume(self, interaction: Interaction):
        """Resumes the current track."""
        await self.service.resume(interaction.guild.id, interaction.user.id)
        await self.send_message(interaction, "Media has been resumed.")

    @app_commands.command(name="shuffle", description="Shuffles the queue")
    @message_error_handler()
    async def shuffle(self, interaction: Interaction):
        """Shuffles the current queue."""
        await self.service.shuffle(interaction.guild.id, interaction.user.id)
        await self.send_message(interaction, "The queue has been shuffled.")

    @app_commands.command(
        name="remove",
        description="Removes the given track number(s) from the queue.",
    )
    @app_commands.describe(
        start="The track number to remove from",
        end="The track number to remove to (optional)",
    )
    @message_error_handler()
    async def remove(
        self,
        interaction: Interaction,
        start: int,
        end: typing.Optional[int],
    ):
        """Removes one or more tracks from the queue."""
        result = await self.service.remove(interaction.guild.id, interaction.user.id, start, end)
        if isinstance(result, int):
            await self.send_message(
                interaction,
                f"Successfully removed **{result}** track{'s' if result > 1 else ''} from the queue.",
            )
        else:
            await self.send_message(
                interaction,
                f"Successfully removed the track [{result['title']}]({result['uri']}) from the queue.",
            )

    @app_commands.command(
        name="move",
        description="Moves the given track to another position in the queue.",
    )
    @app_commands.describe(
        source="The track number to move",
        destination="The position in the queue to move to",
    )
    @message_error_handler()
    async def move(self, interaction: Interaction, source: int, destination: int):
        """Moves a track in the queue to a different position."""
        result = await self.service.move(interaction.guild.id, interaction.user.id, source, destination)
        await self.send_message(
            interaction,
            (
                f"Successfully moved track [{result['title']}]({result['uri']}) "
                f"to position **{result['new_position']}** in the queue."
            ),
        )

    @app_commands.command(
        name="nowplaying",
        description="Sends a message regarding the currently playing song and its progress",
    )
    async def now_playing(self, interaction: Interaction):
        """Displays the currently playing track."""
        player = self.service.get_player_by_guild(interaction.guild.id)

        await interaction.response.send_message(embed=self.embeds.progress(player))
        return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME * 2)

    @app_commands.command(
        name="jump",
        description="Jumps to the given track without skipping songs in the queue",
    )
    @app_commands.describe(position="The queue item number to jump to.")
    @message_error_handler()
    async def jump(self, interaction: Interaction, position: int):
        """Jump to a specific track in the queue."""
        result = await self.service.jump(interaction.guild.id, interaction.user.id, position)
        await self.send_message(
            interaction,
            f"Successfully jumped to the track [{result['title']}]({result['uri']}).",
        )

    @app_commands.command(name="autoplay", description="Toggles auto playing on or off")
    @message_error_handler()
    async def autoplay(self, interaction: Interaction, mode: AutoplayMode):
        """Toggles autoplay on or off."""
        result = await self.service.autoplay(interaction.guild.id, interaction.user.id, mode)
        msg = f"Autoplaying has been {'enabled' if result['autoplay'] else 'disabled'} for the queue."
        if result["loop_on"] and mode == "On":
            msg += "\nNote: Looping is still enabled, and thus takes precedence over autoplay functionality."
        await self.send_message(
            interaction,
            msg,
        )

    @app_commands.command(name="lyrics", description="Retrieves lyrics for a song")
    @app_commands.describe(
        query="The song to search lyrics for. Leaving this blank will fetch lyrics for the current song."
    )
    @message_error_handler(ephemeral=True, followup=True)
    async def lyrics(self, interaction: Interaction, query: typing.Optional[str]):
        """Fetches lyrics for the currently playing song, or a specific song if provided."""
        await interaction.response.defer(thinking=True, ephemeral=True)

        results = await self.service.get_lyrics(interaction.guild.id, query, False)

        lyrics_chunks = format_lyrics_for_display(results.get("lyrics"))
        pages = LyricsMenu(
            source=LyricsPagination(
                interaction=interaction,
                lyrics=lyrics_chunks,
                song=results.get("title"),
                artist=", ".join(results.get("artists", [])) if results.get("artists") else None,
            ),
            interaction=interaction,
        )
        await pages.start(await discord.ext.commands.Context.from_interaction(interaction))

    @app_commands.command(
        name="rewind",
        description="Rewinds the current song. If a time is not provided, this defaults to 15 seconds.",
    )
    @app_commands.describe(time="The amount of time to rewind. Examples: 10 | 1:10 | 1:10:10")
    @message_error_handler()
    async def rewind(self, interaction: Interaction, time: typing.Optional[str]):
        """Rewind the current track by a specific amount of time."""
        converted_time = convert_to_ms(time)
        if converted_time == -1:
            return await self.send_message(
                interaction,
                "Please provide the time to rewind in a suitable format.\nExamples: `10 | 1:10 | 1:10:10`",
                True,
            )

        result = await self.service.rewind(interaction.guild.id, interaction.user.id, converted_time)
        await self.send_message(
            interaction,
            f"Rewinded `{result['amount']}` to `{result['new_time_str']}`.",
        )

    @app_commands.command(
        name="fastforward",
        description="Fast forwards the current song. If a time is not provided, this defaults to 15 seconds.",
    )
    @app_commands.describe(time="The amount of time to fast forward. Examples: 10 | 1:10 | 1:10:10")
    @message_error_handler()
    async def fast_forward(self, interaction: Interaction, time: typing.Optional[str]):
        """Fast forward the current track by a specific amount of time."""
        converted_time = convert_to_ms(time)
        if converted_time == -1:
            return await self.send_message(
                interaction,
                "Please provide the time to rewind in a suitable format.\nExamples: `10 | 1:10 | 1:10:10`",
                True,
            )

        result = await self.service.fast_forward(interaction.guild.id, interaction.user.id, converted_time)
        await self.send_message(
            interaction,
            f"Fast forwarded `{result['amount']}` to `{result['new_time_str']}`.",
        )

    @app_commands.command(
        name="playnext", description="Queues the provided query to play next; does not skip the current song."
    )
    @app_commands.describe(query="A search query or URL to the media.")
    @message_error_handler(ephemeral=False, followup=True)
    async def play_next(self, interaction: Interaction, query: str):
        """Queues a song to be played next in the queue."""
        await interaction.response.defer(thinking=True)

        result = await self.service.play_track(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            query=query,
            index=0,
            handle_new_player=False,
        )

        player = self.service.get_player_by_guild(interaction.guild.id)

        if not result["was_playing"]:
            await self.handle_new_player(player, interaction=interaction)
        else:
            view = QueueAddContainer(self.service,
                                     player, result, self.bot, interaction, position=1, title="Playing Next")
            await interaction.followup.send(view=self.build_view(view))
            await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)

    @app_commands.command(name="playnow", description="Skips the song and plays the requested track immediately.")
    @app_commands.describe(query="A search query or URL to the media.")
    @app_commands.describe(
        continue_skipped="Should the skipped track continue playing after the current track? Defaults to yes."
    )
    @message_error_handler(ephemeral=False, followup=True)
    async def play_now(
        self,
        interaction: Interaction,
        query: str,
        continue_skipped: typing.Optional[Literal["Yes", "No"]] = "Yes",
    ):
        """Skips the current track and plays the requested track immediately."""
        await interaction.response.defer(thinking=True)

        result = await self.service.play_now(
            interaction.guild.id, interaction.user.id, query, continue_skipped == "Yes", handle_new_player=False
        )
        skipped = result["track"]

        player = self.service.get_player_by_guild(interaction.guild.id)

        if not result["was_playing"]:
            return await self.handle_new_player(player, interaction=interaction)

        if continue_skipped == "Yes":
            return await self.send_message(
                interaction,
                f"The track [{skipped['title']}]({skipped['uri']}) will resume playing after the current track.",
                followup=True,
            )

        await self.send_message(
            interaction, f"The track [{skipped['title']}]({skipped['uri']}) has been skipped.", followup=True
        )

    @app_commands.command(name="music", description="Provides a link to the music dashboard")
    async def music(self, interaction: Interaction):
        """Sends a link to the music dashboard for the current guild."""
        view = View()
        view.add_item(
            discord.ui.Button(
                label="Music Dashboard",
                style=discord.ButtonStyle.link,
                # FIXME: change to prod URL
                url=f"https://staging-mocbot.masterofcubesau.com/{interaction.guild.id}/music",
            )
        )
        await interaction.response.send_message(
            embed=self.bot.create_embed(
                "MOCBOT MUSIC",
                f"Use the button below to access the music dashboard for **{interaction.guild.name}**.",
                None,
            ),
            view=view,
        )

    @play.autocomplete("query")
    @play_next.autocomplete("query")
    @play_now.autocomplete("query")
    async def autocomplete_callback(self, _: Interaction, current: str):
        """Autocomplete handler for the play, playnext and playnow commands."""
        if not re.compile(r"https?://(?:www\.)?.+").match(current):
            search = requests.get(
                f"http://suggestqueries.google.com/complete/search?client=youtube&ds=yt&client=firefox&q={current.replace(' ', '%20')}",  # noqa: E501
                timeout=10,
            )
            return [app_commands.Choice(name=result, value=result) for result in search.json()[1]]


async def setup(bot):
    """Setup the Music cog."""
    await bot.add_cog(Music(bot))
