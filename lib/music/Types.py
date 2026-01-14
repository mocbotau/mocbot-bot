from typing import TypedDict, Literal
from ytmusicapi.models import LyricLine
from lavalink import AudioTrack

AutoplayMode = Literal["Off", "On"]
LoopMode = Literal["Off", "Song", "Queue"]


class MusicServiceDefaults(TypedDict):
    """Default settings for a music player"""

    autoplay_load_buffer: int
    autoplay_buffer_min: int
    max_history: int
    seek_time: int
    volume: int


class TrackInfo(TypedDict):
    """Basic information about track(s) returned in a response"""

    id: str
    title: str
    url: str
    duration: int
    requester: int


class PlayResponse(TypedDict):
    """Response structure for play_track method"""

    queue_position: int
    track: AudioTrack  # returns the last track added, if a playlist is added
    was_playing: bool
    playlist_name: str | None
    playlist_length: int | None
    playlist_url: str | None


class SingleTrackResponse(TypedDict):
    """Response structure for methods that return a single track, e.g., skip or previous"""

    id: str
    title: str
    uri: str


class LoopResponse(TypedDict):
    """Response structure for loop method
    We return whether autoplay is on or off to alert the user that looping takes precedence"""

    autoplay_on: bool


class MoveResponse(TypedDict):
    """Response structure for move method"""

    new_position: int
    title: str
    uri: str


class AutoplayResponse(TypedDict):
    """Response structure for autoplay method
    We return whether loop is on or off to alert the user that looping takes precedence"""

    autoplay: bool
    loop_on: bool


class RewindOrFFResponse(TypedDict):
    """Response structure for rewind and fast_forward methods"""

    amount: int
    new_time_str: str


class PlayerStopped(TypedDict):
    """Information about a stopped player"""

    disconnect: bool
    guild_id: int


class LyricsResponse(TypedDict):
    """Response structure for lyrics method"""

    lyrics: str
    title: str
    artists: list[str]


class TimedLyricsResponse(TypedDict):
    """Response structure for lyrics method with timestamps"""

    lyrics: list[LyricLine]
    title: str
    artists: list[str]
