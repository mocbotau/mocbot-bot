import discord
from StringProgressBar import progressBar
from lavalink import DefaultPlayer, AudioTrack

from lib.bot import MOCBOT
from utils.Music import format_duration


class MusicEmbedFactory:
    """Factory class to create various music-related embeds."""

    def __init__(self, bot: "MOCBOT"):
        self.bot = bot

    def base_embed(self, title: str, description: str) -> discord.Embed:
        """Creates a base embed with a standard color and no thumbnail."""
        return self.bot.create_embed(title, description, None)

    def now_playing(self, guild: discord.Guild, player: DefaultPlayer, track=None) -> discord.Embed:
        """Creates an embed for the currently playing track."""
        track = track or player.current
        modifiers = []
        match player.loop:
            case player.LOOP_SINGLE:
                modifiers.append("• Looping Song")
            case player.LOOP_QUEUE:
                modifiers.append("• Looping Queue")

        if player.fetch("autoplay"):
            modifiers.append("• Auto Playing")

        embed = self.base_embed(
            "MOCBOT MUSIC", f"> {'NOW PLAYING' if not player.paused else 'PAUSED'}: [{track.title}]({track.uri})"
        )
        embed.add_field(
            name="Duration", value=format_duration(track.duration) if not track.stream else "LIVE STREAM", inline=True
        )
        embed.add_field(name="Uploader", value=track.author, inline=True)
        if modifiers:
            embed.add_field(name="Modifiers", value="\n".join(modifiers), inline=False)
        embed.set_image(
            url=track.artwork_url if not player.paused else "https://fileshare.masterofcubesau.com/mocbot_pause"
        )
        requester = guild.get_member(track.requester)
        embed.set_footer(text=f"Requested by {requester if requester else f'{self.bot.user}'}")
        return embed

    def queue_add(
        self,
        track: AudioTrack,
        player: DefaultPlayer,
        interaction: discord.Interaction,
        title="ADDED TO QUEUE",
        position: int = None,
    ) -> discord.Embed:
        """Creates an embed for when a track is added to the queue."""

        embed = self.base_embed("MOCBOT MUSIC", f"> {title}: [{track.title}]({track.uri})")
        embed.set_image(url=track.artwork_url)
        embed.add_field(name="POSITION", value=position or len(player.queue), inline=True)
        total_duration = sum(t.duration if not t.stream else 0 for t in player.queue)
        embed.add_field(
            name="QUEUE TIME",
            value=format_duration(total_duration) if total_duration < 86400000 else ">24h",
            inline=True,
        )
        embed.set_footer(text=f"Requested by {interaction.user}")
        return embed

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
