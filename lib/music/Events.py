from typing import Callable, Literal, Union, Dict, Any, List
from lavalink.events import TrackEndEvent, TrackStartEvent
from lavalink import DefaultPlayer

from lib.music.Types import TrackInfo, PlayerStopped

EventName = Literal[
    "player_stopped",
    "track_started",
    "current_position_update",
    "now_playing_update",
    "state_update",
    "player_state_update",
    "queue_update",
    "filters_update",
]

PlayerStatePayload = Dict[str, Any]
StateUpdatePayload = Dict[str, Any]
QueueUpdatePayload = List[Dict[str, Any]]


class EventEmitter:
    """An event emitter for handling music-related events."""

    def __init__(self):
        self._listeners: dict[str, list[Callable]] = {}

    def on(self, event: EventName, callback: Callable) -> None:
        """Register an event listener for a specific event."""
        self._listeners.setdefault(event, []).append(callback)

    def off(self, event: EventName, callback: Callable) -> None:
        """Remove a callback from an event."""
        if event in self._listeners:
            try:
                self._listeners[event].remove(callback)
            except ValueError:
                pass

    async def emit(
        self,
        event: EventName,
        payload: Union[TrackInfo, PlayerStopped, TrackEndEvent, TrackStartEvent, DefaultPlayer, Dict[str, Any], int],
    ) -> None:
        """Emit an event, calling all registered listeners with the provided payload."""
        for cb in self._listeners.get(event, []):
            await cb(payload)
