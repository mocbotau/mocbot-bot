import discord
from lavalink import DefaultPlayer

from lib.bot import MOCBOT
from lib.music.MusicService import MusicService
from lib.music.Types import PlayResponse
from lib.music.containers.base import BaseMusicContainer
from utils.Music import format_duration


class QueueAddContainer(BaseMusicContainer):
    """Container displaying confirmation when tracks are added to the queue."""

    def __init__(
        self,
        service: MusicService,
        player: DefaultPlayer,
        result: PlayResponse,
        bot: MOCBOT,
        interaction: discord.Interaction,
        title: str = "Added to Queue",
        position: int | None = None
    ):
        super().__init__()

        self.service = service
        self.player = player
        self.result = result
        self.bot = bot

        metadata_text = ""
        is_playlist = result.get("playlist_name") is not None
        track = result["track"]

        if is_playlist:
            self.add_item(discord.ui.TextDisplay(f"**{title}**")).add_item(
                discord.ui.TextDisplay(f"### Added [{result['playlist_name']}]({result['playlist_url']})")
            )
            metadata_text = f"-# Tracks Added\n**{result['playlist_length']}**\n"
        else:
            self.add_item(discord.ui.TextDisplay(f"**{title}**")).add_item(
                discord.ui.TextDisplay(f"### Added [{track.title}]({track.uri})")
            )
            metadata_text = "-# Position in Queue\n**" + \
                            (str(position) if position is not None else str(len(player.queue))) + "**\n"

        queue_time = sum(t.duration if not t.stream else 0 for t in player.queue)

        self.add_item(
            discord.ui.Section(
                discord.ui.TextDisplay(metadata_text),
                discord.ui.TextDisplay(
                    "-# Queue Time\n**"
                    + (format_duration(queue_time) if queue_time < 86400000 else ">24h")
                    + "**"
                ),
                accessory=discord.ui.Thumbnail(track.artwork_url),
            )
        )
        self.add_item(discord.ui.Separator())
        self.add_item(
            discord.ui.TextDisplay(
                "-# Requested by "
                + interaction.user.mention
            )
        )

        buttons = discord.ui.ActionRow()
        self.top = discord.ui.Button(
            emoji=discord.PartialEmoji(name="top", id=1460911129521033290),
            style=discord.ButtonStyle.secondary,
            label="Move to Top",
            disabled=result.get("queue_position") == 1,
        )
        self.top.callback = self.handle_top

        self.play_now = discord.ui.Button(
            emoji=discord.PartialEmoji(name="playnow", id=1460911127545516032),
            style=discord.ButtonStyle.secondary,
            label="Play Now",
        )
        self.play_now.callback = self.handle_play_now

        self.delete = discord.ui.Button(
            emoji=discord.PartialEmoji(name="delete", id=1460911131433500830),
            style=discord.ButtonStyle.danger,
        )
        self.delete.callback = self.handle_delete

        buttons.add_item(self.top).add_item(self.play_now).add_item(self.delete)

        if not is_playlist:
            self.add_item(buttons)

    async def handle_top(self, interaction: discord.Interaction):
        """Handle top button press"""
        await self.service.move(interaction.guild.id, interaction.user.id, self.result.get("queue_position"), 1)
        await interaction.response.defer()
        await interaction.message.delete()
        track = self.result["track"]
        await interaction.followup.send(
            embed=self.bot.create_embed("MOCBOT MUSIC", f"[{track.title}]({track.uri}) moved to top."), ephemeral=True
        )

    async def handle_play_now(self, interaction: discord.Interaction):
        """Handle play now button press"""
        await interaction.response.defer()
        await self.service.remove(interaction.guild.id, interaction.user.id, self.result.get("queue_position"))
        await self.service.play_now(interaction.guild.id, interaction.user.id,
                                    self.result["track"].uri, handle_new_player=False)
        await interaction.message.delete()

    async def handle_delete(self, interaction: discord.Interaction):
        """Handle delete button press"""
        await self.service.remove(interaction.guild.id, interaction.user.id, self.result.get("queue_position"))
        track = self.result["track"]
        await interaction.response.defer()
        await interaction.message.delete()
        await interaction.followup.send(
            embed=self.bot.create_embed("MOCBOT MUSIC",
                                        f"[{track.title}]({track.uri}) deleted from queue."), ephemeral=True
        )
