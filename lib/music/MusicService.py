import asyncio
import logging
import random
import os
import re
from typing import TYPE_CHECKING, Union

from ytmusicapi import YTMusic
import lavalink
from lavalink import DefaultPlayer, LoadType, listener, LoadResult, AudioTrack
from lavalink.events import TrackStartEvent, QueueEndEvent, TrackEndEvent

from utils.APIHandler import ArchiveAPI
from utils.ConfigHandler import Config
from utils.Music import is_youtube_url, queue_length_msg, format_duration, create_id
from lib.music.Decorators import event_handler
from lib.music.Lavalink import LavalinkVoiceClient
from lib.music.Filters import filter_manager
from lib.music.Events import EventEmitter
from lib.music.Exceptions import InternalError, UserError
from lib.music.Types import (
    PlayMultipleResponse,
    PlayResponse,
    PlayerStopped,
    SingleTrackResponse,
    MusicServiceDefaults,
    LyricsResponse,
    TimedLyricsResponse,
    LoopMode,
    LoopResponse,
    MoveResponse,
    AutoplayMode,
    AutoplayResponse,
    RewindOrFFResponse,
)

if TYPE_CHECKING:
    from lib.bot import MOCBOT


class MusicService:
    """Core music service management"""

    def __init__(self, bot: "MOCBOT"):
        self.bot = bot
        self.emitter = EventEmitter()
        self.logger = logging.getLogger(__name__)
        self.player_defaults: MusicServiceDefaults = {
            "autoplay_load_buffer": 5,
            "autoplay_buffer_min": 2,
            "max_history": 30,
            "seek_time": 15000,  # in milliseconds
            "volume": 10,
        }

        with open(os.environ["LAVALINK_PASSWORD"], "r", encoding="utf-8") as f:
            lavalink_pass = f.read().strip()

        self.lavalink = lavalink.Client(bot.user.id)
        self.lavalink.add_node(
            Config.fetch()["LAVALINK"]["HOST"],
            Config.fetch()["LAVALINK"]["PORT"],
            lavalink_pass,
            "eu",
            "default-node",
        )
        self.lavalink.add_event_hooks(self)

        self.emitter.on("player_stopped", self.end_session)
        self.sessions = {}

    async def ensure_voice(self, guild_id: int, user_id: int, should_connect: bool = False) -> DefaultPlayer:
        """Ensure the bot is connected to a voice channel and return the player."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            raise InternalError("This command can only be used inside a Discord server.")

        user = guild.get_member(user_id)
        if not user or not user.voice or not user.voice.channel:
            raise UserError("Join a voice channel first.")

        v_client = guild.voice_client
        if not v_client:
            if not should_connect:
                raise UserError("MOCBOT is not connected to a voice channel.")

            permissions = user.voice.channel.permissions_for(guild.me)
            if not permissions.connect or not permissions.speak:
                raise UserError("Please provide MOCBOT with CONNECT and SPEAK permissions.")

            if guild_id not in self.sessions:
                res = ArchiveAPI.post("/sessions", body={"guildId": guild_id})
                if res.get("ID") is not None:
                    self.sessions[guild_id] = res.get("ID")

            await user.voice.channel.connect(cls=LavalinkVoiceClient)
        else:
            if v_client.channel.id != user.voice.channel.id:
                raise UserError("You need to be in my voice channel to execute that command.")

        player: DefaultPlayer = self.get_player_by_guild(guild_id)
        if not player:
            player = self.lavalink.player_manager.create(guild_id)

        return player

    @listener(QueueEndEvent)
    async def queue_end_hook(self, event: QueueEndEvent):
        """Handle the end of the music queue."""
        guild_id = event.player.guild_id
        guild = self.bot.get_guild(guild_id)
        player = event.player

        emit_payload = {"disconnect": True, "player": player}

        if player.fetch("autoplay"):
            autoplay_queue = player.fetch("autoplay_queue", [])
            if not autoplay_queue:
                asyncio.create_task(self.emitter.emit("player_stopped", emit_payload))
                self.logger.error("[MUSIC] [{%s} // {%s}] Autoplay queue is empty, disconnecting.", guild, guild_id)
                return

            track = autoplay_queue.pop(0)
            player.add(requester=None, track=track)

            if not player.is_playing:
                await player.play()
        else:
            asyncio.create_task(self.emitter.emit("player_stopped", emit_payload))

    @event_handler("player_stopped")
    async def end_session(self, data: PlayerStopped):
        """End the music session for a guild."""
        guild_id = data.get("player").guild_id
        if guild_id is None:
            return

        session_id = self.sessions.get(guild_id)
        if session_id is None:
            return

        ArchiveAPI.patch(f"/sessions/{session_id}")

        del self.sessions[guild_id]

    @listener(TrackStartEvent)
    async def track_start_hook(self, event: TrackStartEvent):
        """Handle the start of a new track."""
        guild_id = event.player.guild_id
        guild = self.bot.get_guild(guild_id)

        # we fetch the full player so we can run clear_filters if needed. The BasePlayer class
        # returned from event.player is missing some methods.
        player: DefaultPlayer = self.get_player_by_guild(guild_id)
        if not player:
            self.logger.error("[MUSIC] [%s] // {%s}] Player not found on track start.", guild, guild_id)
            return

        track = event.track

        self.logger.info("[MUSIC] [%s] // %s] Playing %s - %s", guild, guild_id, track.title, track.uri)

        if track.stream:
            await player.clear_filters()
        if track.position != 0:
            await player.seek(track.position)
            track.position = 0  # Reset position after seeking

        asyncio.create_task(self.emitter.emit("track_started", player))
        asyncio.create_task(self.handle_autoplay(event))

        # Don't add to session if looping single track. We would've already added it on first play, when loop was off
        if player.loop == player.LOOP_SINGLE:
            return

        asyncio.create_task(self.add_track_to_session(guild_id, track))

    async def add_track_to_session(self, guild_id: int, track: AudioTrack):
        """Add a track to the current session."""
        session_id = self.sessions.get(guild_id)
        if session_id is None:
            return

        users_in_voice_channel = []
        guild = self.bot.get_guild(guild_id)
        if guild:
            voice_channel = guild.voice_client.channel if guild.voice_client else None
            if voice_channel:
                users_in_voice_channel = [member.id for member in voice_channel.members
                                          if not member.id == self.bot.user.id]

        res = ArchiveAPI.post(
            f"/sessions/{session_id}/tracks",
            body={
                "source": track.source_name,
                "sourceId": track.identifier,
                "title": track.title,
                "artist": track.author,
                "url": track.uri,
                "durationMs": track.duration,
                "queuedByUser": track.requester if track.requester else self.bot.user.id,
                "listenerIds": users_in_voice_channel,
            },
        )

        if res.get("ID") is not None:
            track.extra["archive_track_id"] = res.get("ID")

    @listener(TrackEndEvent)
    async def track_end_hook(self, event: TrackEndEvent):
        """Handle the end of a track."""
        if event.track is None:
            return  # skip adding to avoid errors

        # Skip adding to history if this track end was caused by a call to previous
        if event.player.fetch("skip_history_update", False):
            event.player.store("skip_history_update", False)
            return

        # Don't add to history if looping single track
        if event.player.loop == event.player.LOOP_SINGLE:
            return

        recently_played = event.player.fetch("recently_played", [])

        if len(recently_played) >= self.player_defaults["max_history"]:
            recently_played.pop(0)

        event.track.position = 0  # Reset position before adding to history
        recently_played.append(event.track)
        event.player.store("recently_played", recently_played)
        asyncio.create_task(self.end_track_session(event.player.guild_id, event.track))

    async def end_track_session(self, guild_id: int, track: AudioTrack):
        """Mark a track as ended in the current session."""
        session_id = self.sessions.get(guild_id)
        if session_id is None:
            return

        archive_track_id = track.extra.get("archive_track_id")
        if archive_track_id is None:
            return

        ArchiveAPI.patch(f"/tracks/{archive_track_id}")

    async def handle_autoplay(self, event: TrackEndEvent):
        """Handles saving a few tracks to an auto-play queue to speed up auto-queueing."""
        guild_id = event.player.guild_id
        guild = self.bot.get_guild(guild_id)
        player = event.player

        autoplay_queue = player.fetch("autoplay_queue", [])
        # We'll refill when there's 2 or less tracks left
        if len(autoplay_queue) > self.player_defaults["autoplay_buffer_min"]:
            return

        track = player.current

        if not is_youtube_url(track.uri):
            youtube_res = await player.node.get_tracks(f"ytsearch:{track.title} {track.author}")
            track = youtube_res.tracks[0]

        results = await player.node.get_tracks(track.uri + f"&list=RD{track.identifier}")
        if not results or not results.tracks:
            self.logger.error("[MUSIC] [%s] // {%s}] Autoplay failed to find related tracks.", guild, guild_id)

        max_index = min(len(results.tracks), self.player_defaults["autoplay_load_buffer"]) + 1

        # we skip the first track as it's the current one
        new_tracks = results.tracks[1:max_index]
        for track in new_tracks:
            track.extra["id"] = create_id()
        autoplay_queue.extend(new_tracks)
        player.store("autoplay_queue", autoplay_queue)

    def get_player_by_guild(self, guild_id: int) -> DefaultPlayer | None:
        """Get the lavalink player for a specific guild."""
        return self.lavalink.player_manager.get(guild_id)

    async def _validate_guild_and_user(self, guild_id: int, user_id: int):
        """Validate guild and user existence. Returns (guild, user) tuple."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            raise InternalError(f"Guild with ID {guild_id} not found")

        user = guild.get_member(user_id)
        if not user:
            raise InternalError(f"User with ID {user_id} not found in guild {guild_id}")

        return guild, user

    def _prepare_query(self, query: str) -> tuple[str, str]:
        """Prepare query for track search. Returns (prepared_query, original_query) tuple."""
        query = query.strip("<>")
        original_query = query
        if not re.compile(r"https?://(?:www\.)?.+").match(query):
            query = f"ytsearch:{query}"
        return query, original_query

    async def _finalize_playback(self, player: DefaultPlayer, handle_new_player: bool) -> bool:
        """Finalize playback by setting volume and starting player if needed.
        Returns whether the player was already playing."""
        await player.set_volume(self.player_defaults["volume"])
        is_playing = player.is_playing

        if not player.is_playing:
            player.store("handle_new_player", handle_new_player)
            await player.play()
        else:
            asyncio.create_task(self.emitter.emit("queue_update", player))

        return is_playing

    async def play_track(
        self, guild_id: int, user_id: int, query: str, index: int = None, handle_new_player=True, is_play_now=False,
    ) -> PlayResponse:
        """Handle playing a track or playlist based on a search query or URL.
        handle_new_player indicates whether to handle the new player logic, which by default should be True"""
        await self._validate_guild_and_user(guild_id, user_id)
        player = await self.ensure_voice(guild_id, user_id, should_connect=True)

        if player.queue:
            if index is not None and (index < 0 or index > len(player.queue)):
                raise UserError(f"Invalid index. {queue_length_msg(len(player.queue))}")

        query, original_query = self._prepare_query(query)
        results = await player.node.get_tracks(query)

        if not results or not results.tracks:
            raise UserError(f"No media matching the search query `{original_query}` was found")

        if results.load_type == LoadType.PLAYLIST and is_play_now:
            raise UserError("You can only use playnow with single tracks, not playlists. Use the play command instead.")
        if results.load_type != LoadType.PLAYLIST:
            results.tracks = [results.tracks[0]]

        for track in results.tracks:
            track.extra["id"] = create_id()
            player.add(requester=user_id, track=track, index=index)

        is_playing = await self._finalize_playback(player, handle_new_player)

        res = {"queue_position": index + 1 if index is not None else len(player.queue),
               "track": results.tracks[-1],
               "was_playing": is_playing}

        if results.load_type == LoadType.PLAYLIST:
            res["playlist_name"] = results.playlist_info.name
            res["playlist_length"] = len(results.tracks)
            res["playlist_url"] = original_query

        return res

    async def play_tracks(
        self, guild_id: int, user_id: int, queries: list[str], handle_new_player=True, initial_batch_size: int = 2,
    ) -> PlayMultipleResponse:
        """Handle playing a list of queries.
        Queues the first few tracks immediately and starts playback, then queues the rest in the background.
        initial_batch_size: Number of tracks to queue before starting playback (default: 2)
        """
        await self._validate_guild_and_user(guild_id, user_id)
        player = await self.ensure_voice(guild_id, user_id, should_connect=True)

        if not queries:
            raise UserError("No queries provided to play.")

        initial_queries = queries[:initial_batch_size]
        remaining_queries = queries[initial_batch_size:]

        failed_count = 0
        total_tracks = 0
        last_results = None

        for query in initial_queries:
            query, _ = self._prepare_query(query)
            results = await player.node.get_tracks(query)

            if not results or not results.tracks:
                failed_count += 1
                continue

            if results.load_type != LoadType.PLAYLIST:
                results.tracks = [results.tracks[0]]

            for track in results.tracks:
                track.extra["id"] = create_id()
                player.add(requester=user_id, track=track)
                total_tracks += 1

            last_results = results

        is_playing = await self._finalize_playback(player, handle_new_player)

        if remaining_queries:
            asyncio.create_task(self._queue_remaining_tracks(player, user_id, remaining_queries))

        res = {"playlist_length": total_tracks + len(remaining_queries),
               "failed": failed_count,
               "track": last_results.tracks[-1] if last_results else None,
               "was_playing": is_playing}

        return res

    async def _queue_remaining_tracks(self, player: DefaultPlayer, user_id: int, queries: list[str]):
        """Background task to queue remaining tracks after initial batch is playing."""
        failed = 0
        for query in queries:
            query, _ = self._prepare_query(query)
            results = await player.node.get_tracks(query)

            if not results or not results.tracks:
                failed += 1
                continue

            if results.load_type != LoadType.PLAYLIST:
                results.tracks = [results.tracks[0]]

            for track in results.tracks:
                track.extra["id"] = create_id()
                player.add(requester=user_id, track=track)

        asyncio.create_task(self.emitter.emit("queue_update", player))

    async def search(self, query: str) -> LoadResult | None:
        """Search for tracks based on a query or URL."""
        results = await self.lavalink.get_tracks(query)
        if not results or not results.tracks:
            return None

        return results

    async def skip(self, guild_id: int, user_id: int, position: int = 1) -> SingleTrackResponse:
        """Skip the current track or a specific track in the queue."""
        player = await self.ensure_voice(guild_id, user_id)

        if position < 1 or (
            position > len(player.queue) and not player.fetch("autoplay") and player.loop == player.LOOP_NONE
        ):
            raise UserError("You may only skip to a track within the queue.")

        player.queue = player.queue[position - 1 :]
        skipped = player.current
        await player.skip()

        return {
            "id": skipped.extra.get("id", create_id()),
            "title": skipped.title,
            "uri": skipped.uri,
        }

    async def previous(self, guild_id: int, user_id: int) -> SingleTrackResponse:
        """Play the previous track from history."""
        player = await self.ensure_voice(guild_id, user_id)

        recently_played = player.fetch("recently_played", [])
        if not recently_played:
            raise UserError("There are no recently played tracks to go back to.")

        track = recently_played.pop()
        player.store("recently_played", recently_played)
        player.queue.insert(0, player.current)

        player.store("skip_history_update", True)
        await player.play(track)

        return {
            "id": track.extra.get("id", create_id()),
            "title": track.title,
            "uri": track.uri,
        }

    async def seek(self, guild_id: int, user_id: int, position: int) -> int:
        """Seek to a specific position in the current track. Position is in milliseconds."""
        player = await self.ensure_voice(guild_id, user_id)

        if position < 0 or position > player.current.duration:
            raise UserError(f"The seek position must be between 0 and {format_duration(player.current.duration)}.")

        if not player.current.is_seekable or player.current.stream:
            raise UserError("The current track is not seekable.")

        await player.seek(position)
        asyncio.create_task(self.emitter.emit("current_position_update", player))

        return position

    async def loop(self, guild_id: int, user_id: int, mode: LoopMode) -> LoopResponse:
        """Set the loop mode for the player."""
        player = await self.ensure_voice(guild_id, user_id)

        match mode:
            case "Off":
                player.set_loop(0)
            case "Song":
                player.set_loop(1)
            case "Queue":
                player.set_loop(2)
            case _:
                raise UserError("Invalid loop mode specified.")

        asyncio.create_task(self.emitter.emit("now_playing_update", player))
        asyncio.create_task(self.emitter.emit("player_state_update", player))
        return {
            # We return the autoplay status to notify users that loop mode takes precedence
            "autoplay_on": player.fetch("autoplay", False),
        }

    async def stop(self, guild_id: int, user_id: int, disconnect=False) -> None:
        """Clear the player, and optionally disconnect from voice."""
        player = await self.ensure_voice(guild_id, user_id)

        if not disconnect and not player.is_playing:
            raise UserError("MOCBOT is not playing any music.")

        player.queue.clear()
        # reset custom stored values
        player.store("autoplay_queue", [])
        player.store("recently_played", [])
        player.store("autoplay", False)
        player.store("skip_history_update", False)
        player.store("handle_new_player", True)
        await player.stop()

        asyncio.create_task(self.emitter.emit("player_stopped", {"disconnect": disconnect, "player": player}))

    async def pause(self, guild_id: int, user_id: int) -> None:
        """Pause the current track."""
        player = await self.ensure_voice(guild_id, user_id)

        if player.paused:
            raise UserError("Playback is already paused. Use the resume command to resume the music.")

        await player.set_pause(True)

        asyncio.create_task(self.emitter.emit("now_playing_update", player))
        asyncio.create_task(self.emitter.emit("player_state_update", player))

    async def resume(self, guild_id: int, user_id: int) -> None:
        """Resume the current track."""
        player = await self.ensure_voice(guild_id, user_id)

        if not player.paused:
            raise UserError("Playback is not paused. Use the pause command to pause the music.")

        await player.set_pause(False)

        asyncio.create_task(self.emitter.emit("now_playing_update", player))
        asyncio.create_task(self.emitter.emit("player_state_update", player))

    async def shuffle(self, guild_id: int, user_id: int) -> None:
        """Shuffle the current queue."""
        player = await self.ensure_voice(guild_id, user_id)

        if len(player.queue) < 2:
            raise UserError("You need at least 2 tracks in the queue to shuffle.")

        random.shuffle(player.queue)
        asyncio.create_task(self.emitter.emit("queue_update", player))

    async def remove(self, guild_id: int, user_id: int, start: int, end: int = None) -> int | SingleTrackResponse:
        """Remove one or more tracks from the queue."""
        player = await self.ensure_voice(guild_id, user_id)

        if start < 1 or start > len(player.queue):
            raise UserError(f"Invalid start position. {queue_length_msg(len(player.queue))}")

        if end is None:
            removed_track = player.queue.pop(start - 1)
            asyncio.create_task(self.emitter.emit("queue_update", player))

            return {
                "id": removed_track.extra.get("id", create_id()),
                "title": removed_track.title,
                "uri": removed_track.uri,
            }

        if end < start or end > len(player.queue):
            raise UserError(f"IInvalid end position. {queue_length_msg(len(player.queue))}")

        player.queue = player.queue[: start - 1] + player.queue[end:]
        del player.queue[start - 1 : end]

        asyncio.create_task(self.emitter.emit("queue_update", player))
        return end - start + 1

    async def move(self, guild_id: int, user_id: int, src: int, dest: int) -> MoveResponse:
        """Move a track from one position in the queue to another."""
        player = await self.ensure_voice(guild_id, user_id)

        if len(player.queue) < 2:
            raise UserError("You need at least 2 tracks in the queue to move tracks.")

        if src == dest:
            raise UserError("The source and destination positions must be different.")

        if src < 1 or src > len(player.queue) or dest < 1 or dest > len(player.queue):
            raise UserError(f"Invalid positions in the queue. {queue_length_msg(len(player.queue))}")

        player.queue.insert(dest - 1, track := player.queue.pop(src - 1))

        asyncio.create_task(self.emitter.emit("queue_update", player))
        return {"new_position": dest, "title": track.title, "uri": track.uri}

    async def jump(self, guild_id: int, user_id: int, position: int) -> SingleTrackResponse:
        """Jump to a specific track in the queue."""
        player = await self.ensure_voice(guild_id, user_id)

        if position < 1 or position > len(player.queue):
            raise UserError(f"Invalid position in the queue. {queue_length_msg(len(player.queue))}")

        await player.play(track := player.queue.pop(position - 1), replace=True)

        return {
            "id": track.extra.get("id", create_id()),
            "title": track.title,
            "uri": track.uri,
        }

    async def clear_queue(self, guild_id: int, user_id: int) -> None:
        """Clear the entire queue."""
        player = await self.ensure_voice(guild_id, user_id)

        if not player.queue or len(player.queue) == 0:
            raise UserError("The queue is already empty.")

        player.queue.clear()
        asyncio.create_task(self.emitter.emit("queue_update", player))

        return

    async def autoplay(self, guild_id: int, user_id: int, mode: AutoplayMode = None) -> AutoplayResponse:
        """Enable or disable autoplay mode. If no mode is specified, toggle the current state."""
        player = await self.ensure_voice(guild_id, user_id)

        if mode is None:
            player.store("autoplay", not player.fetch("autoplay", False))
        else:
            match mode:
                case "Off":
                    player.store("autoplay", False)
                case "On":
                    player.store("autoplay", True)

        asyncio.create_task(self.emitter.emit("now_playing_update", player))
        asyncio.create_task(self.emitter.emit("player_state_update", player))

        return {
            "autoplay": player.fetch("autoplay", False),
            # We return the loop status to notify users that loop mode takes precedence
            "loop_on": player.loop != player.LOOP_NONE,
        }

    async def rewind(self, guild_id: int, user_id: int, time: int = None) -> RewindOrFFResponse:
        """Rewind the current track by a specified number of milliseconds"""
        player = await self.ensure_voice(guild_id, user_id)
        if time is None:
            time = self.player_defaults["seek_time"]

        if not player.current.is_seekable or player.current.stream:
            raise UserError("The current track is not seekable.")

        new_time = max(0, player.position - time)
        new_time_fmt = format_duration(new_time)
        amount = format_duration(time)

        await player.seek(new_time)

        asyncio.create_task(self.emitter.emit("player_state_update", player))

        return {"amount": amount, "new_time_str": new_time_fmt}

    async def fast_forward(self, guild_id: int, user_id: int, time: int = None) -> RewindOrFFResponse:
        """Fast forward the current track by a specified number of milliseconds"""
        player = await self.ensure_voice(guild_id, user_id)
        if time is None:
            time = self.player_defaults["seek_time"]

        if not player.current.is_seekable or player.current.stream:
            raise UserError("The current track is not seekable.")

        new_time = min(player.current.duration, player.position + time)
        new_time_fmt = format_duration(new_time)
        amount = format_duration(time)

        if new_time > player.current.duration:
            remaining_time = format_duration(player.current.duration - player.position)
            raise UserError(f"The current track only has `{remaining_time}` time left.")

        await player.seek(new_time)

        asyncio.create_task(self.emitter.emit("player_state_update", player))

        return {"amount": amount, "new_time_str": new_time_fmt}

    async def play_now(
        self, guild_id: int, user_id: int, query: str, continue_skipped: bool = True, handle_new_player=True
    ) -> PlayResponse:
        """Play a track immediately, skipping the current track."""
        player = await self.ensure_voice(guild_id, user_id, should_connect=True)

        if continue_skipped:
            player.store("skip_history_update", True)

        response = await self.play_track(guild_id, user_id,
                                         query, index=0, handle_new_player=handle_new_player, is_play_now=True)
        if not response["was_playing"]:
            return response

        skipped = player.current
        skipped.position = player.position

        await player.skip()

        if continue_skipped:
            player.queue.insert(0, skipped)

        return {"queue_position": len(player.queue) - 1, "track": skipped, "was_playing": response["was_playing"]}

    async def apply_filters(self, guild_id: int, user_id: int, filters: list[str]) -> None:
        """Apply audio filters to the current player."""
        player = await self.ensure_voice(guild_id, user_id)

        await player.clear_filters()
        player.store("filters", [])

        invalid_filters = await filter_manager.apply_filters(player, filters)
        if invalid_filters:
            raise UserError(f"Invalid filters specified: {', '.join(invalid_filters)}")

        asyncio.create_task(self.emitter.emit("filters_update", player))

    async def get_lyrics(
        self, guild_id: int, query: str | None, timed: bool
    ) -> Union[LyricsResponse, TimedLyricsResponse]:
        """Get lyrics for the current track, or search for lyrics based on a query."""

        player = self.get_player_by_guild(guild_id)
        if not query and (not player or not player.current):
            raise UserError("No track is currently playing. If you want to search for lyrics, please provide a query.")

        err_msg = f"No lyrics found for {f'`{query}`' if query is not None else 'the current track'}."

        ytmusic = YTMusic()

        search = query if query else f"{player.current.title} - {player.current.author}"

        t = ytmusic.search(search, filter="songs", limit=1)
        # fetch the youtube music video id
        if not t or not t[0].get("videoId"):
            raise UserError(err_msg)

        # fetch the watch list, as that contains the lyrics key
        w = ytmusic.get_watch_playlist(t[0].get("videoId"), limit=1)
        if not w or not w.get("lyrics"):
            raise UserError(err_msg)

        lyrics = ytmusic.get_lyrics(w.get("lyrics"), timestamps=timed)
        if not lyrics or not lyrics.get("lyrics"):
            raise UserError(err_msg)

        artists = [a.get("name") for a in t[0].get("artists", []) if a and a.get("name")]

        return {
            "lyrics": lyrics.get("lyrics"),
            "title": t[0].get("title"),
            "artists": artists,
        }
