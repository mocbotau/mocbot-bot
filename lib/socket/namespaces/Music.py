import asyncio
import logging
import os

from dataclasses import dataclass
from hashlib import sha256
from typing import Optional, TYPE_CHECKING, Any, Dict, List, Set, Callable
from functools import wraps

import socketio
from socketio.exceptions import ConnectionRefusedError as SocketIOConnectionRefusedError
from lavalink import DefaultPlayer, AudioTrack
from lib.music.Decorators import event_handler
from lib.music.Exceptions import UserError, InternalError
from lib.music.Types import TimedLyricsResponse

if TYPE_CHECKING:
    from lib.bot import MOCBOT
    from lib.music.MusicService import MusicService


@dataclass
class ActionContext:
    """Context object containing validated data for action methods"""

    guild_id: int
    socket_id: str
    user_id: Optional[int]


def music_action(requires_user_id: bool = True):
    """Decorator to handle common validation and error handling for music actions"""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(self: "MusicSocket", _socket_id: str, data: dict):
            try:
                socket_id = data.get(
                    "socket_id"
                )  # this is different, as it is the original socket id from the frontend
                if not socket_id:
                    self.logger.warning("Missing socket_id in data: %s", data)
                    return

                guild_id = data.get("guild_id")
                if not guild_id:
                    await self.emit("error", {"room": socket_id, "message": "Guild ID required"})
                    return

                user_id = None
                if requires_user_id:
                    user_id = data.get("user_id")
                    if not user_id:
                        await self.emit("error", {"room": socket_id, "message": "User ID required"})
                        return

                self.ctx = ActionContext(
                    guild_id=int(guild_id), user_id=int(user_id) if user_id is not None else None, socket_id=socket_id
                )

                await func(self, data)

            except UserError as e:
                await self.emit("user_error", {"room": socket_id, "message": str(e)})
            except InternalError as e:
                self.logger.error("Internal error in %s: %s", func.__name__, e)
                await self.emit(
                    "error", {"room": socket_id, "message": "An error occurred while processing your request."}
                )
            except (ConnectionError, TimeoutError) as e:
                self.logger.error("Connection error in %s: %s", func.__name__, e)
                await self.emit("error", {"room": socket_id, "message": "Connection error"})
            except Exception as e:
                self.logger.error("Error in %s: %s", func.__name__, e)
                await self.emit("error", {"room": socket_id, "message": "Internal error"})
                raise

        return wrapper

    return decorator


class MusicSocket(socketio.AsyncNamespace):
    """
    Socket.IO namespace for music control

    Important to note:
    Methods decorated with @music_action will have self.ctx populated with an ActionContext
    containing validated guild_id, socket_id, and optionally user_id.

    The socket_id in self.ctx is the original socket ID from the frontend, not the one sent by the middleware server.
    This is important for us to keep track of, so that we can send responses back to the correct client for events
    that we do not wish to be broadcast to all clients in a guild room (e.g., errors, search results, etc).

    In most other instances, we instead use the guild_id to emit to all clients in that guild room.
    """

    def __init__(self, namespace: str, bot: "MOCBOT", service: "MusicService") -> None:
        super().__init__(namespace)
        self.bot: "MOCBOT" = bot
        self.service: "MusicService" = service
        self._update_task: Optional[asyncio.Task] = None
        self._active_guilds: Set[int] = set()
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.ctx: Optional[ActionContext] = None

        # Register event handlers from methods decorated with @event_handler
        for attr_name in dir(self):
            method = getattr(self, attr_name)
            if callable(method) and hasattr(method, "event_names"):
                event_names = getattr(method, "event_names")
                for event_name in event_names:
                    self.service.emitter.on(event_name, method)

    async def on_connect(self, socket_id: str, environ: Dict[str, Any], auth: Optional[Dict[str, str]] = None) -> None:
        """Handle client connection with authentication"""
        if not auth or "token" not in auth:
            self.logger.warning(
                "Unauthorised connection from %s - missing auth token", environ.get("REMOTE_ADDR", None)
            )
            raise SocketIOConnectionRefusedError("Missing auth token")

        socket_key = auth["token"]
        with open(os.environ["SOCKET_KEY"], "r", encoding="utf-8") as f:
            config_key = f.read().strip()

        if sha256(socket_key.encode("utf-8")).hexdigest() != config_key:
            self.logger.warning("Unauthorised connection from %s - invalid token", environ.get("REMOTE_ADDR", None))
            raise SocketIOConnectionRefusedError("Invalid token")

        if self._update_task is None or self._update_task.done():
            self._update_task = asyncio.create_task(self._periodic_updates())

        self.logger.info("Music controller client connected: %s", socket_id)

    async def on_disconnect(self, socket_id: str) -> None:
        """Handle client disconnection"""
        self.logger.info("Music controller client disconnected: %s", socket_id)

    async def on_join_guild(self, socket_id: str, data: Dict[str, Any]) -> None:
        """Client joins a guild room for updates"""
        guild_id = data.get("guild_id")
        self.logger.info("Client %s joined guild %s", socket_id, guild_id)
        if guild_id:
            self._active_guilds.add(int(guild_id))

    async def on_leave_guild(self, socket_id: str, data: Dict[str, Any]) -> None:
        """Client leaves a guild room"""
        guild_id = data.get("guild_id")
        self.logger.info("Client %s left guild %s", socket_id, guild_id)
        if guild_id:
            self._active_guilds.discard(int(guild_id))

    async def _periodic_updates(self) -> None:
        while True:
            try:
                for guild_id in list(self._active_guilds):
                    player: DefaultPlayer = self.service.get_player_by_guild(guild_id)
                    if player and player.is_playing and not player.paused:
                        await self.emit_current_position(player)
            except Exception:
                self.logger.exception("Error in periodic updates")
                raise

            await asyncio.sleep(10)

    async def _build_player_state(self, player: Optional[DefaultPlayer]) -> Dict[str, Any]:
        if not player:
            return {
                "autoplay": "Off",
                "isConnected": False,
                "isPlaying": False,
                "paused": False,
                "position": 0,
                "repeat": 0,
                "voiceChannel": None,
                "volume": 10,
            }

        return {
            "autoplay": player.fetch("autoplay", "Off"),
            "isConnected": True,
            "isPlaying": player.is_playing,
            "paused": player.paused,
            "position": player.position,
            "repeat": player.loop,
            "voiceChannel": (self.bot.get_channel(player.channel_id).name if player.channel_id else None),
            "volume": player.volume,
        }

    async def _build_current_track(self, player: Optional[DefaultPlayer]) -> Optional[Dict[str, Any]]:
        if not player or not player.current:
            return None

        requester = self.bot.get_user(player.current.requester)
        return {
            "id": player.current.extra.get("id", ""),
            "title": player.current.title,
            "artist": player.current.author,
            "duration": player.current.duration,
            "uri": player.current.uri,
            "requester": requester.name if requester else self.bot.user.name,
            "stream": player.current.stream,
            "thumbnail": player.current.artwork_url,
        }

    async def _build_queue(self, player: Optional[DefaultPlayer]) -> List[Dict[str, Any]]:
        return [] if not player or not player.queue else self._convert_track_list(player.queue)

    async def _build_recently_played(self, player: Optional[DefaultPlayer]) -> List[Dict[str, Any]]:
        if not player:
            return []

        recent_tracks = player.fetch("recently_played", [])
        if not recent_tracks:
            return []

        return self._convert_track_list(reversed(recent_tracks))

    async def _build_filters(self, player: Optional[DefaultPlayer]) -> List[str]:
        if not player:
            return []

        return player.fetch("filters", [])

    def _convert_track_list(self, tracks: List[AudioTrack]) -> List[Dict[str, Any]]:
        formatted_tracks = []

        for i, track in enumerate(tracks):
            requester = self.bot.get_user(track.requester)
            formatted_tracks.append(
                {
                    "index": i,
                    "id": track.extra.get("id", ""),
                    "title": track.title,
                    "artist": track.author,
                    "duration": track.duration,
                    "position": track.position,
                    "stream": track.stream,
                    "uri": track.uri,
                    "requester": requester.name if requester else self.bot.user.name,
                    "thumbnail": track.artwork_url,
                }
            )

        return formatted_tracks

    @event_handler("state_update")
    @event_handler("track_started")
    async def emit_state_update(self, data: Any = None, guild_id: int = None) -> None:
        """Emit full state update including player state, current track, and queue"""
        if isinstance(data, dict) and "player" in data:
            player = data["player"]
        else:
            player = data

        state = {
            **await self._build_player_state(player),
            "currentSong": await self._build_current_track(player),
            "filters": await self._build_filters(player),
            "queue": await self._build_queue(player),
            "recentlyPlayed": await self._build_recently_played(player),
        }
        await self.emit(
            "state_update",
            {"room": str(guild_id if guild_id is not None else (player.guild_id if player else None)), "state": state},
        )

    @event_handler("player_stopped")
    async def handle_player_stopped(self, data: Dict[str, Any]) -> None:
        """Handle player stopped event"""
        await self.emit_state_update(data.get("player"))

    @event_handler("player_state_update")
    async def emit_player_state(self, player: DefaultPlayer) -> None:
        """Emit player state update"""
        state = await self._build_player_state(player)
        await self.emit("player_state_update", {"room": str(player.guild_id), "state": state})

    @event_handler("queue_update")
    async def emit_queue(self, player: DefaultPlayer) -> None:
        """Emit queue update"""
        queue = await self._build_queue(player)
        await self.emit("queue_update", {"room": str(player.guild_id), "queue": queue})

    @event_handler("current_position_update")
    async def emit_current_position(self, player: DefaultPlayer) -> None:
        """Emit current track position update"""
        player = self.service.get_player_by_guild(player.guild_id)
        position = player.position if player else 0
        await self.emit("current_position_update", {"room": str(player.guild_id), "position": position})

    @event_handler("filters_update")
    async def emit_filters_update(self, player: DefaultPlayer) -> None:
        """Emit current active filters"""
        filters = await self._build_filters(player)
        await self.emit("filters_update", {"room": str(player.guild_id), "filters": filters})

    @music_action(requires_user_id=False)
    async def on_lavalink_search(self, data: Dict[str, Any]) -> None:
        """Search for tracks using lavalink"""
        query = data.get("query")
        if not query:
            await self.emit("error", {"room": self.ctx.socket_id, "message": "Search query required"})
            return

        results = await self.service.search(query)
        if not results:
            await self.emit("search_results", {"room": self.ctx.socket_id, "tracks": []})
            return

        tracks = []
        for track in results.tracks[:10]:
            tracks.append(
                {
                    "title": track.title,
                    "artist": track.author,
                    "duration": track.duration,
                    "uri": track.uri,
                    "thumbnail": track.artwork_url,
                }
            )

        await self.emit("search_results", {"room": self.ctx.socket_id, "tracks": tracks})

    @music_action(requires_user_id=True)
    async def on_add_track(self, data: Dict[str, Any]) -> None:
        """Play a track using the core music service"""
        query = data.get("query")
        if not query:
            await self.emit("user_error", {"room": self.ctx.socket_id, "message": "Track query required"})
            return

        index = data.get("index")
        self._active_guilds.add(str(self.ctx.guild_id))

        await self.service.play_track(self.ctx.guild_id, self.ctx.user_id, query, index)
        # We need a separate event to notify clients a track was added to update UI loading states
        await self.emit("track_added", {"room": self.ctx.socket_id})

    @music_action(requires_user_id=True)
    async def on_play_now(self, data: Dict[str, Any]) -> None:
        """Play a track immediately, skipping the current track"""
        query = data.get("query")
        if not query:
            await self.emit("user_error", {"room": self.ctx.socket_id, "message": "Track query required"})
            return

        continue_skipped = data.get("continue_skipped", True)

        self._active_guilds.add(str(self.ctx.guild_id))

        await self.service.play_now(self.ctx.guild_id, self.ctx.user_id, query, continue_skipped=continue_skipped)
        await self.emit("track_added", {"room": self.ctx.socket_id})

    @music_action(requires_user_id=False)
    async def on_get_player_state(self, _data: Dict[str, Any]) -> None:
        """Get current player state for a guild"""
        await self.emit_state_update(self.service.get_player_by_guild(self.ctx.guild_id), guild_id=self.ctx.guild_id)

    @music_action(requires_user_id=True)
    async def on_resume(self, _data: Dict[str, Any]) -> None:
        """Resume playback"""
        await self.service.resume(self.ctx.guild_id, self.ctx.user_id)

    @music_action(requires_user_id=True)
    async def on_pause(self, _data: Dict[str, Any]) -> None:
        """Pause playback"""
        await self.service.pause(self.ctx.guild_id, self.ctx.user_id)

    @music_action(requires_user_id=True)
    async def on_skip(self, _data: Dict[str, Any]) -> None:
        """Skip to next track"""
        await self.service.skip(self.ctx.guild_id, self.ctx.user_id)

    @music_action(requires_user_id=True)
    async def on_previous(self, _data: Dict[str, Any]) -> None:
        """Go to previous track"""
        await self.service.previous(self.ctx.guild_id, self.ctx.user_id)

    @music_action(requires_user_id=True)
    async def on_seek(self, data: Dict[str, Any]) -> None:
        """Seek to position in current track"""
        position = data.get("position")
        if position is None:
            await self.emit("user_error", {"room": self.ctx.socket_id, "message": "Position required"})
            return

        await self.service.seek(self.ctx.guild_id, self.ctx.user_id, position)

    @music_action(requires_user_id=True)
    async def on_set_loop(self, data: Dict[str, Any]) -> None:
        """Set loop mode (0=off, 1=single, 2=queue)"""
        loop_mode = data.get("loop_mode")
        await self.service.loop(self.ctx.guild_id, self.ctx.user_id, loop_mode)

    @music_action(requires_user_id=True)
    async def on_set_autoplay(self, data: Dict[str, Any]) -> None:
        """Set autoplay mode"""
        mode = data.get("mode")

        if not mode or mode not in ["Off", "Related", "Recommended"]:
            await self.emit("user_error", {"room": self.ctx.socket_id, "message": "Invalid autoplay mode"})
            return

        await self.service.autoplay(self.ctx.guild_id, self.ctx.user_id, mode)

    @music_action(requires_user_id=True)
    async def on_shuffle_queue(self, _data: Dict[str, Any]) -> None:
        """Shuffle the current queue"""
        await self.service.shuffle(self.ctx.guild_id, self.ctx.user_id)

    @music_action(requires_user_id=True)
    async def on_move_track(self, data: Dict[str, Any]) -> None:
        """Move track within the queue"""
        old_index = data.get("old_index")
        new_index = data.get("new_index")

        if old_index is None or new_index is None:
            await self.emit("user_error", {"room": self.ctx.socket_id, "message": "Both indices are required"})
            return

        await self.service.move(self.ctx.guild_id, self.ctx.user_id, old_index + 1, new_index + 1)

    @music_action(requires_user_id=True)
    async def on_remove_track(self, data: Dict[str, Any]) -> None:
        """Remove track from queue"""
        index = data.get("index")

        if index is None:
            await self.emit("user_error", {"room": self.ctx.socket_id, "message": "Track index required"})
            return

        await self.service.remove(self.ctx.guild_id, self.ctx.user_id, index + 1)

    @music_action(requires_user_id=True)
    async def on_clear_queue(self, _data: Dict[str, Any]) -> None:
        """Clear the entire queue"""
        await self.service.clear_queue(self.ctx.guild_id, self.ctx.user_id)

    @music_action(requires_user_id=True)
    async def on_disconnect_guild(self, _data: Dict[str, Any]) -> None:
        """Client leaves a guild room and disconnects the bot from the voice channel"""
        await self.service.stop(self.ctx.guild_id, self.ctx.user_id, disconnect=True)

    @music_action(requires_user_id=False)
    async def on_get_lyrics(self, _data: Dict[str, Any]) -> None:
        """Get lyrics for the current track, with timing if available"""
        guild_id = self.ctx.guild_id
        lyrics = None

        empty_response = {"room": str(guild_id), "lyrics": [], "title": None, "artists": None}

        try:
            lyrics: TimedLyricsResponse = await self.service.get_lyrics(guild_id, query=None, timed=True)
        except UserError:
            await self.emit("lyrics_result", empty_response)
            return

        if not lyrics or not lyrics.get("lyrics"):
            await self.emit("lyrics_result", empty_response)
            return

        result = []
        for line in lyrics.get("lyrics", []):
            result.append({"start": line.start_time, "end": line.end_time, "text": line.text})

        await self.emit(
            "lyrics_result",
            {"room": str(guild_id), "lyrics": result, "title": lyrics.get("title"), "artists": lyrics.get("artists")},
        )

    @music_action(requires_user_id=True)
    async def on_apply_filters(self, data: Dict[str, Any]) -> None:
        """Apply audio filters to the player"""
        filter_names = data.get("filters", [])
        if not isinstance(filter_names, list):
            await self.emit("user_error", {"room": self.ctx.socket_id, "message": "Filters must be a list"})
            return

        invalid_filters = await self.service.apply_filters(self.ctx.guild_id, self.ctx.user_id, filter_names)
        if invalid_filters:
            await self.emit(
                "user_error", {"room": self.ctx.socket_id, "message": f"Invalid filters: {', '.join(invalid_filters)}"}
            )

        await self.emit("filters_success", {"room": self.ctx.socket_id})
