import discord
from StringProgressBar import progressBar
from lavalink import DefaultPlayer

from lib.bot import MOCBOT
from utils.Music import format_duration


class MusicEmbedFactory:
    """Factory class to create various music-related embeds."""

    def __init__(self, bot: MOCBOT):
        self.bot = bot

    def base_embed(self, title: str, description: str) -> discord.Embed:
        """Creates a base embed with a standard color and no thumbnail."""
        return self.bot.create_embed(title, description, None)

    def progress(self, player: DefaultPlayer) -> discord.Embed:
        """Creates an embed showing the current progress of the playing track."""
        progress_bar = progressBar.splitBar(player.current.duration, int(player.position), size=15)
        duration_text = format_duration(int(player.position))
        total_duration = format_duration(int(player.current.duration))

        embed = self.base_embed("MOCBOT MUSIC", f"> NOW PLAYING: [{player.current.title}]({player.current.uri})")
        embed.add_field(
            name="Requested By",
            value=f"<@{player.current.requester}>" if player.current.requester else self.bot.user.mention,
            inline=True,
        )
        embed.add_field(name="Uploader", value=player.current.author, inline=True)
        embed.add_field(
            name="Progress",
            value=f"{duration_text} {progress_bar[0]} {'LIVE STREAM' if player.current.stream else total_duration}",
            inline=False,
        )
        embed.set_thumbnail(url=player.current.artwork_url)
        return embed
