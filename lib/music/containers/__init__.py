"""Music UI containers for Discord v2 components."""

from .base import BaseMusicContainer, PaginatedContainer
from .now_playing import NowPlayingContainer
from .queue_add import QueueAddContainer
from .queue_display import QueueContainer
from .recents_display import RecentsContainer

__all__ = [
    "BaseMusicContainer",
    "PaginatedContainer",
    "NowPlayingContainer",
    "QueueAddContainer",
    "QueueContainer",
    "RecentsContainer",
]
