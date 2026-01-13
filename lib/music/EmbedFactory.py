import discord
from StringProgressBar import progressBar
from lavalink import DefaultPlayer, AudioTrack

from lib.bot import MOCBOT
from lib.music.MusicService import MusicService
from utils.Music import format_duration


class NowPlayingView(discord.ui.Container):
    service: MusicService

    def __init__(self, service: MusicService, player: DefaultPlayer, track: AudioTrack, bot: MOCBOT):
        super().__init__()

        self.service = service
        self.player = player
        self.track = track
        self.bot = bot

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

        self.accent_color = 0xDC3145
        self.add_item(buttons)

    async def handle_prev(self, interaction: discord.Interaction):
        """Handle previous track button press"""
        await self.service.previous(interaction.guild.id, interaction.user.id)
        await interaction.response.defer()
        await interaction.message.edit(view=self)

    async def handle_play_pause(self, interaction: discord.Interaction):
        """Handle play/pause button press"""
        if self.player.paused:
            await self.service.resume(interaction.guild.id, interaction.user.id)
        else:
            await self.service.pause(interaction.guild.id, interaction.user.id)

        await interaction.response.defer()
        await interaction.message.edit(view=self)

    async def handle_next(self, interaction: discord.Interaction):
        """Handle next track button press"""
        await self.service.skip(interaction.guild.id, interaction.user.id)
        await interaction.response.defer()
        await interaction.message.edit(view=self)

    async def handle_autoplay(self, interaction: discord.Interaction):
        """Handle autoplay toggle button press"""
        await self.service.autoplay(interaction.guild.id, interaction.user.id)
        await interaction.response.defer()
        await interaction.message.edit(view=self)

# class QueueAddView(discord.ui.Container):
#     service: MusicService

#     def __init__(self,
#             service: MusicService,
#             player: DefaultPlayer,
#             track: AudioTrack,
#             bot: MOCBOT,
#             interaction: discord.Interaction,
#             position: int | None = None):
#         super().__init__()

#         self.service = service
#         self.player = player
#         self.track = track
#         self.bot = bot

#         self.add_item(discord.ui.TextDisplay("**Added to Queue**")).add_item(
#             discord.ui.TextDisplay(f"### [{track.title}]({track.uri})")
#         )

#         queue_time = sum(t.duration if not t.stream else 0 for t in player.queue)

#         self.add_item(
#             discord.ui.Section(
#                 discord.ui.TextDisplay(f"-# Position\n**{position or len(player.queue)}**"),
#                 discord.ui.TextDisplay(
#                     "-# Queue Time\n**"
#                     + (format_duration(queue_time) if queue_time < 86400000 else ">24h")
#                     + "**"
#                 ),
#                 accessory=discord.ui.Thumbnail(track.artwork_url),
#             )
#         )
#         self.add_item(discord.ui.Separator())
#         self.add_item(
#             discord.ui.TextDisplay(
#                 "-# Requested by "
#                 + interaction.user
#             )
#         )

#         buttons = discord.ui.ActionRow()
#         self.prev_button = discord.ui.Button(
#             emoji=discord.PartialEmoji(name="prev", id=1460504545489846398),
#             style=discord.ButtonStyle.secondary,
#             disabled=(not player.fetch("recently_played", []))
#         )
#         self.prev_button.callback = self.handle_prev

#         self.next_button = discord.ui.Button(
#             emoji=discord.PartialEmoji(name="next", id=1460504537784909834),
#             style=discord.ButtonStyle.secondary,
#             disabled=(len(player.queue) == 0 and not player.fetch("autoplay") and player.loop is player.LOOP_NONE),
#         )
#         self.next_button.callback = self.handle_next

#         self.autoplay_button = discord.ui.Button(
#             emoji=discord.PartialEmoji(name="autoplay", id=1460506638652805243),
#             label="Autoplay",
#             style=player.fetch("autoplay") and discord.ButtonStyle.blurple or discord.ButtonStyle.secondary,
#         )
#         self.autoplay_button.callback = self.handle_autoplay

#         buttons.add_item(self.prev_button).add_item(self.play_pause_button).add_item(self.next_button).add_item(self.autoplay_button)

#         self.add_item(buttons)

#     async def handle_prev(self, interaction: discord.Interaction):
#         """Handle previous track button press"""
#         await self.service.previous(interaction.guild.id, interaction.user.id)
#         await interaction.response.defer()
#         await interaction.message.edit(view=self)

#     async def handle_play_pause(self, interaction: discord.Interaction):
#         """Handle play/pause button press"""
#         if self.player.paused:
#             await self.service.resume(interaction.guild.id, interaction.user.id)
#         else:
#             await self.service.pause(interaction.guild.id, interaction.user.id)

#         await interaction.response.defer()
#         await interaction.message.edit(view=self)

#     async def handle_next(self, interaction: discord.Interaction):
#         """Handle next track button press"""
#         await self.service.skip(interaction.guild.id, interaction.user.id)
#         await interaction.response.defer()
#         await interaction.message.edit(view=self)

#     async def handle_autoplay(self, interaction: discord.Interaction):
#         """Handle autoplay toggle button press"""
#         await self.service.autoplay(interaction.guild.id, interaction.user.id)
#         await interaction.response.defer()
#         await interaction.message.edit(view=self)


class MusicEmbedFactory:
    """Factory class to create various music-related embeds."""

    def __init__(self, bot: "MOCBOT"):
        self.bot = bot

    def base_embed(self, title: str, description: str) -> discord.Embed:
        """Creates a base embed with a standard color and no thumbnail."""
        return self.bot.create_embed(title, description, None)

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
