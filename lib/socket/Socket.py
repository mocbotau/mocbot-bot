import logging
import socketio

from aiohttp import web
from utils.ConfigHandler import Config

from .namespaces.Music import MusicSocket
from .namespaces.Verification import Verification

SIO = socketio.AsyncServer(
    cors_allowed_origins=[
        f'http://[{Config.fetch()["SOCKET"]["HOST"]}:{Config.fetch()["SOCKET"]["PORT"]}',
        "http://localhost:3000",
    ]
)

APP = web.Application()
RUNNER = web.AppRunner(APP)
SIO.attach(APP)

NAMESPACE_REGISTRY = {
    "music": MusicSocket,
    "verification": Verification,
}


class Socket:
    """Manages the Socket.IO server and its namespaces."""

    HOST = Config.fetch()["SOCKET"]["HOST"]
    PORT = Config.fetch()["SOCKET"]["PORT"]

    @staticmethod
    async def start(bot):
        """Starts the Socket.IO server and registers namespaces."""
        await bot.wait_until_ready()

        for name, cls in NAMESPACE_REGISTRY.items():
            if name == "music":
                namespace_instance = cls(f"/{name}", bot, bot.music_service)
            else:
                namespace_instance = cls(f"/{name}")

            SIO.register_namespace(namespace_instance)
            logging.getLogger(__name__).info("Initialized /%s namespace", name)

        await RUNNER.setup()
        site = web.TCPSite(RUNNER, Socket.HOST, Socket.PORT)
        await site.start()
        logging.getLogger(__name__).info("[SOCKET] Listening on %s:%s", Socket.HOST, Socket.PORT)

    @staticmethod
    async def emit(*args, **kwargs):
        """Emits an event to all connected clients."""
        await SIO.emit(*args, **kwargs)
