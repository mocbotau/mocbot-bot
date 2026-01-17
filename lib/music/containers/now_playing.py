import discord
from lavalink import DefaultPlayer, AudioTrack

from lib.bot import MOCBOT
from lib.music.Decorators import message_error_handler
from lib.music.MusicService import MusicService
from lib.music.containers.base import BaseMusicContainer
from utils.Music import format_duration


class NowPlayingContainer(BaseMusicContainer):
    """Container displaying the currently playing track with playback controls."""

    def __init__(self, service: MusicService, player: DefaultPlayer, track: AudioTrack, bot: MOCBOT):
        super().__init__()

        self.service = service
        self.player = player
        self.track = track
        self.bot = bot
        self.logger = bot.logger

        modifier = ""
        match player.loop:
            case player.LOOP_SINGLE:
                modifier += " • Looping Song"
            case player.LOOP_QUEUE:
                modifier += " • Looping Queue"

        status = "Paused" if player.paused else "Now Playing"
        duration_text = (
            "LIVE STREAM"
            if track.stream
            else format_duration(track.duration)
        )

        self.add_item(discord.ui.TextDisplay(f"**{status}**")).add_item(
            discord.ui.TextDisplay(f"### [{track.title}]({track.uri})")
        )

        self.add_item(
            discord.ui.Section(
                discord.ui.TextDisplay(f"-# Duration\n**{duration_text}**"),
                discord.ui.TextDisplay(
                    "-# Uploader\n**"
                    + track.author[:40]
                    + ("…" if len(track.author) > 40 else "")
                    + "**"
                ),
                accessory=discord.ui.Thumbnail(track.artwork_url),
            )
        )
        self.add_item(discord.ui.Separator())
        self.add_item(
            discord.ui.TextDisplay(
                "-# Requested by "
                + (
                    f"<@{player.current.requester}>"
                    if player.current.requester
                    else bot.user.mention
                ) + modifier
            )
        )

        buttons = discord.ui.ActionRow()
        self.prev_button = discord.ui.Button(
            emoji=discord.PartialEmoji(name="prev", id=1460504545489846398),
            style=discord.ButtonStyle.secondary,
            disabled=(not player.fetch("recently_played", []))
        )
        self.prev_button.callback = self.handle_prev

        self.play_pause_button = discord.ui.Button(
            emoji=discord.PartialEmoji(
                name="resume",
                id=1460506628569956385)
            if player.paused else discord.PartialEmoji(name="pause", id=1460506640750088419),
            style=discord.ButtonStyle.secondary,
        )
        self.play_pause_button.callback = self.handle_play_pause

        self.next_button = discord.ui.Button(
            emoji=discord.PartialEmoji(name="next", id=1460504537784909834),
            style=discord.ButtonStyle.secondary,
            disabled=(len(player.queue) == 0 and not player.fetch("autoplay") and player.loop is player.LOOP_NONE),
        )
        self.next_button.callback = self.handle_next

        self.autoplay_button = discord.ui.Button(
            emoji=discord.PartialEmoji(name="autoplay", id=1460506638652805243),
            label="Autoplay",
            style=player.fetch("autoplay") and discord.ButtonStyle.blurple or discord.ButtonStyle.secondary,
        )
        self.autoplay_button.callback = self.handle_autoplay

        buttons.add_item(self.prev_button)
        buttons.add_item(self.play_pause_button)
        buttons.add_item(self.next_button)
        buttons.add_item(self.autoplay_button)
        buttons.add_item(
            discord.ui.Button(
                label="Dashboard",
                style=discord.ButtonStyle.link,
                emoji=discord.PartialEmoji(name="controls", id=1460506636639539427),
                url=f"https://staging-mocbot.masterofcubesau.com/{player.guild_id}/music",
            )
        )

        self.add_item(buttons)

    @message_error_handler(ephemeral=True, followup=True)
    async def handle_prev(self, interaction: discord.Interaction):
        """Handle previous track button press"""
        await interaction.response.defer()
        await self.service.previous(interaction.guild.id, interaction.user.id)
        await interaction.message.edit(view=self)

    @message_error_handler(ephemeral=True, followup=True)
    async def handle_play_pause(self, interaction: discord.Interaction):
        """Handle play/pause button press"""
        await interaction.response.defer()
        if self.player.paused:
            await self.service.resume(interaction.guild.id, interaction.user.id)
        else:
            await self.service.pause(interaction.guild.id, interaction.user.id)

        await interaction.message.edit(view=self)

    @message_error_handler(ephemeral=True, followup=True)
    async def handle_next(self, interaction: discord.Interaction):
        """Handle next track button press"""
        await interaction.response.defer()
        await self.service.skip(interaction.guild.id, interaction.user.id)
        await interaction.message.edit(view=self)

    @message_error_handler(ephemeral=True, followup=True)
    async def handle_autoplay(self, interaction: discord.Interaction):
        """Handle autoplay toggle button press"""
        await interaction.response.defer()
        await self.service.autoplay(interaction.guild.id, interaction.user.id)
        await interaction.message.edit(view=self)
