import discord
from lavalink import DefaultPlayer, AudioTrack

from lib.bot import MOCBOT
from lib.music.Decorators import message_error_handler
from lib.music.MusicService import MusicService
from lib.music.containers.base import BaseMusicContainer
from utils.Music import format_duration

EMPTY_LEFT = "<:progressbaremptyleft:1487774443374776471>"
FULL_LEFT = "<:progressbarfullleft:1487774452857962537>"
EMPTY = "<:progressbarempty:1487774441139077243>"
FULL = "<:progressbarfull:1487774446860107891>"
CURRENT = "<:progressbarcurrent:1487774439306170398>"
EMPTY_RIGHT = "<:progressbaremptyright:1487774445060882594>"
FULL_RIGHT = "<:progressbarfullright:1487774456234512474>"


class NowPlayingContainer(BaseMusicContainer):
    """Container displaying the currently playing track with playback controls."""

    REFRESH_INTERVAL = 10
    PROGRESS_BAR_GRADUATIONS = 12

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

        self.add_item(discord.ui.TextDisplay(f"**{status}**")).add_item(
            discord.ui.TextDisplay(f"### [{track.title}]({track.uri})")
        )

        self.add_item(
            discord.ui.Section(
                discord.ui.TextDisplay(
                    "-# Uploader\n**"
                    + track.author[:40]
                    + ("…" if len(track.author) > 40 else "")
                    + "**"
                    + "\n\n\n"
                    + "-# " + self._create_progress_bar(int(player.position), int(track.duration), track.stream)
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

        if player.fetch("autoplay", "Off") != "Off" and (len(player.queue) == 0 and player.loop is player.LOOP_NONE):
            autoplay_mode = player.fetch("autoplay", "Recommended")
            if autoplay_mode == "Recommended":
                self.add_item(
                    discord.ui.TextDisplay(
                        "-# Autoplay will continue with tracks from: " + ", ".join(
                            list(dict.fromkeys(player.fetch("recommended_artists", []))))
                    )
                )
            elif autoplay_mode == "Related":
                self.add_item(
                    discord.ui.TextDisplay(
                        "-# Autoplay will continue with similar tracks related to the current track"
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

        autoplay_off = player.fetch("autoplay", "Off") == "Off"
        self.next_button = discord.ui.Button(
            emoji=discord.PartialEmoji(name="next", id=1460504537784909834),
            style=discord.ButtonStyle.secondary,
            disabled=(len(player.queue) == 0 and autoplay_off and player.loop is player.LOOP_NONE),
        )
        self.next_button.callback = self.handle_next

        autoplay_mode = player.fetch("autoplay", "Off")
        autoplay_label_map = {
            "Off": "Off",
            "Related": "Related",
            "Recommended": "Recommended"
        }

        self.autoplay_button = discord.ui.Button(
            emoji=discord.PartialEmoji(name="autoplay", id=1460506638652805243),
            label=f"Autoplay: {autoplay_label_map.get(autoplay_mode, 'Off')}",
            style=discord.ButtonStyle.blurple if autoplay_mode != "Off" else discord.ButtonStyle.secondary,
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

    def _refresh_view(self) -> discord.ui.LayoutView:
        """Create a new view with updated now playing container."""
        new_container = NowPlayingContainer(self.service, self.player, self.track, self.bot)
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(new_container)
        return view

    def _create_progress_bar(self, position: int, duration: int, live_stream: bool) -> str:
        """Create a fixed-width progress bar based on playback position."""
        if duration <= 0:
            return EMPTY_LEFT + (EMPTY * (self.PROGRESS_BAR_GRADUATIONS - 1)) + EMPTY_RIGHT

        intervals = duration // self.PROGRESS_BAR_GRADUATIONS
        if position >= max(0, duration - 5000) or live_stream:  # 5 second buffer at the end to ensure it fills
            current_interval = self.PROGRESS_BAR_GRADUATIONS
        else:
            current_interval = (position // intervals) if intervals > 0 else 0

        current_interval = max(0, min(self.PROGRESS_BAR_GRADUATIONS, current_interval))

        elapsed = format_duration(position)
        total = "LIVE" if live_stream else format_duration(duration)

        progress_bar = f"{elapsed}\t"
        progress_bar += EMPTY_LEFT if current_interval == 0 and not live_stream else FULL_LEFT

        for i in range(1, self.PROGRESS_BAR_GRADUATIONS):
            if i < current_interval:
                progress_bar += FULL
            elif i == current_interval:
                progress_bar += CURRENT
            else:
                progress_bar += EMPTY

        progress_bar += FULL_RIGHT if current_interval == self.PROGRESS_BAR_GRADUATIONS else EMPTY_RIGHT
        progress_bar += f"\t{total}"

        return progress_bar

    @message_error_handler(ephemeral=True, followup=True)
    async def handle_prev(self, interaction: discord.Interaction):
        """Handle previous track button press"""
        await self.service.previous(interaction.guild.id, interaction.user.id)

    @message_error_handler(ephemeral=True, followup=True)
    async def handle_play_pause(self, interaction: discord.Interaction):
        """Handle play/pause button press"""
        if self.player.paused:
            await self.service.resume(interaction.guild.id, interaction.user.id)
        else:
            await self.service.pause(interaction.guild.id, interaction.user.id)

        await self._defer_and_update_view(interaction, self._refresh_view())

    @message_error_handler(ephemeral=True, followup=True)
    async def handle_next(self, interaction: discord.Interaction):
        """Handle next track button press"""
        await self.service.skip(interaction.guild.id, interaction.user.id)

    @message_error_handler(ephemeral=True, followup=True)
    async def handle_autoplay(self, interaction: discord.Interaction):
        """Handle autoplay mode cycle button press - cycles through Off -> Related -> Recommended -> Off"""
        current_mode = self.player.fetch("autoplay", "Off")
        mode_cycle = {
            "Off": "Related",
            "Related": "Recommended",
            "Recommended": "Off"
        }
        next_mode = mode_cycle.get(current_mode, "Related")

        await self.service.autoplay(interaction.guild.id, interaction.user.id, next_mode)
        await self._defer_and_update_view(interaction, self._refresh_view())
