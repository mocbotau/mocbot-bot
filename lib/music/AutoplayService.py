import random
import logging
from collections import deque
from cachetools import TTLCache
from lavalink import DefaultPlayer, AudioTrack
from utils.APIHandler import ArchiveAPI
from utils.Music import create_id, is_youtube_url


class AutoplayService:
    """Service to handle autoplaying recommended tracks based on artist recommendations."""

    def __init__(
        self,
        cache_ttl_seconds: int = 15 * 60,
        discovery_probability: float = 0.15,
        artist_cooldown_size: int = 3,
        intent_buffer_size: int = 3,
    ):
        self.logger = logging.getLogger(__name__)
        self.node = None

        self.discovery_probability = discovery_probability
        self.artist_cooldown_size = artist_cooldown_size
        self.intent_buffer_size = intent_buffer_size

        # guild_id -> recommendations
        self._cache = TTLCache(maxsize=128, ttl=cache_ttl_seconds)

        self._intent_buffer: dict[int, deque[str]] = {}

        # guild_id -> deque[artist]
        self._artist_cooldowns: dict[str, deque[str]] = {}

    def set_node(self, player: DefaultPlayer):
        """Set the Lavalink node to use for track searches."""
        self.node = player.node

    def peek_intent(self, guild_id: int) -> list[str]:
        """Returns upcoming artist intents."""
        buffer = self._intent_buffer.get(guild_id)

        if not buffer:
            return []
        return list(buffer)

    async def get_next(self,
                       guild_id: int,
                       mode: str = "Recommended",
                       current_track: AudioTrack | None = None) -> AudioTrack | None:
        """
        Fetch the next track based on the specified autoplay mode.
        """
        if mode == "Related":
            return await self._get_related_track(current_track)

        return await self._get_recommended_track(guild_id)

    async def _get_recommended_track(self, guild_id: int) -> AudioTrack | None:
        """
        Fetch a track from recommended artists.
        """
        await self.ensure_intent_buffer(guild_id)
        artist = self._intent_buffer[guild_id].popleft()

        query = self._build_search_query(artist)
        track = await self._search_track(query)

        return track

    async def _get_related_track(self, current_track: AudioTrack | None) -> AudioTrack | None:
        """
        Fetch a single related track based on the current track using YouTube mix.
        This is used for the "Related" autoplay mode.
        """
        if not current_track:
            self.logger.warning("No current track provided for Related mode")
            return None

        track = current_track

        if not is_youtube_url(track.uri):
            youtube_res = await self.node.get_tracks(f"ytsearch:{track.title} {track.author}")
            if not youtube_res or not youtube_res.tracks:
                self.logger.error("Failed to find YouTube version of track: %s", track.title)
                return None
            track = youtube_res.tracks[0]

        # Get related tracks from YouTube mix
        mix_url = track.uri + f"&list=RD{track.identifier}"
        results = await self.node.get_tracks(mix_url)

        if not results or not results.tracks or len(results.tracks) < 2:
            self.logger.error("Failed to find related tracks for: %s", track.title)
            return None

        # Skip the first track (it's the current one) and pick a random one from the next few
        valid_tracks = [t for t in results.tracks[1:6] if self._valid_track(t)]

        if not valid_tracks:
            self.logger.warning("No valid related tracks found for: %s", track.title)
            return None

        selected_track = random.choice(valid_tracks)
        selected_track.extra["id"] = create_id()

        self.logger.info("Selected related track: %s", selected_track.title)
        return selected_track

    async def ensure_intent_buffer(self, guild_id: int):
        """Ensure the intent buffer is filled for the guild."""
        artists = await self._get_recommendations(guild_id)
        if not artists:
            return None

        buffer = self._intent_buffer.get(guild_id)
        if buffer is None:
            buffer = deque(maxlen=self.intent_buffer_size)
            self._intent_buffer[guild_id] = buffer

        while len(buffer) < buffer.maxlen:
            artist = self._choose_artist(guild_id, artists)
            buffer.append(artist)

    async def _get_recommendations(self, guild_id: int) -> list[dict]:
        if guild_id not in self._cache:
            raw_recommendations = await self._fetch_recommendations(guild_id)
            self._cache[guild_id] = self._normalise_weights(raw_recommendations.get("recommended_artists", []))
        return self._cache[guild_id]

    async def _fetch_recommendations(self, guild_id: int) -> dict:
        return ArchiveAPI.get(f"/guilds/{guild_id}/artists/recommended")

    def _normalise_weights(self, artists: list[dict]) -> list[dict]:
        total = sum(a["weight"] for a in artists)
        if total <= 0:
            return []

        return [
            {
                "artist": a["artist"],
                "p": a["weight"] / total,
            }
            for a in artists
        ]

    def _choose_artist(self, _guild_id: int, artists: list[dict]) -> str:
        # cooldown = self._artist_cooldowns.setdefault(
        #     guild_id,
        #     deque(maxlen=self.artist_cooldown_size),
        # )

        # candidates = [
        #     a for a in artists if a["artist"] not in cooldown
        # ] or artists  # fallback if all are in cooldown

        choices = [a["artist"] for a in artists]
        weights = [a["p"] for a in artists]

        artist = random.choices(choices, weights=weights, k=1)[0]
        # cooldown.append(artist)
        return artist

    def _build_search_query(self, artist: str) -> str:
        return f"{artist} official audio"

    async def _search_track(self, query: str):
        results = await self.node.get_tracks(f"ytsearch:{query}")

        if not results or not results.tracks:
            return None

        valid = [
            t for t in results.tracks
            if self._valid_track(t)
        ]

        if not valid:
            return None

        return random.choice(valid[:5])

    @staticmethod
    def _valid_track(track: AudioTrack) -> bool:
        title = track.title.lower()
        return not any(
            bad in title
            for bad in (
                "live",
                "playlist",
                "full album",
                "compilation",
                "album",
                "reaction",
            )
        )
