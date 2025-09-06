from typing import Callable, Awaitable, TYPE_CHECKING
import asyncio
import discord
from lavalink.filters import (
    LowPass,
    Rotation,
    Timescale,
    Vibrato,
    Karaoke,
    Equalizer,
    Tremolo,
)
from lavalink import DefaultPlayer

if TYPE_CHECKING:
    from lib.music.MusicService import MusicService


class Filter:
    """Represents a single audio filter with its metadata and application logic."""

    def __init__(self, name: str, label: str, description: str, apply_func: Callable[[DefaultPlayer], Awaitable[None]]):
        self.name = name
        self.label = label
        self.description = description
        self.apply_func = apply_func

    async def apply(self, player: DefaultPlayer) -> None:
        """Apply this filter to the player."""
        await self.apply_func(player)

    def to_select_option(self, player: DefaultPlayer) -> discord.SelectOption:
        """Convert this filter to a Discord SelectOption."""
        return discord.SelectOption(
            label=self.label,
            description=self.description,
            value=self.name,
            default=self.name in player.fetch("filters", []),
        )


class FilterManager:
    """Centralized manager for all audio filters."""

    def __init__(self):
        self._filters: dict[str, Filter] = {}
        self._register_default_filters()

    def _register_default_filters(self):
        """Register all default filters."""

        def _set_player_filter_property(player: DefaultPlayer, filter_name: str):
            """Helper to set a filter property on the player."""
            filters = player.fetch("filters", [])
            player.store("filters", filters + [filter_name])

        async def low_pass_apply(player: DefaultPlayer):
            """Applies a low pass filter to the player."""
            lp_filter = LowPass()
            lp_filter.update(smoothing=50)
            await player.set_filter(lp_filter)
            _set_player_filter_property(player, "low_pass")

        async def eight_d_apply(player: DefaultPlayer):
            """Applies an 8D audio filter to the player."""
            eight_d_filter = Rotation()
            eight_d_filter.update(rotation_hz=0.2)
            await player.set_filter(eight_d_filter)
            _set_player_filter_property(player, "eight_d")

        async def nightcore_apply(player: DefaultPlayer):
            """Applies a nightcore filter to the player."""
            nightcore_filter = Timescale()
            nightcore_filter.update(speed=1.2, pitch=1.2, rate=1)
            await player.set_filter(nightcore_filter)
            _set_player_filter_property(player, "nightcore")

        async def vibrato_apply(player: DefaultPlayer):
            """Applies a vibrato filter to the player."""
            vibrato_filter = Vibrato()
            vibrato_filter.update(depth=1, frequency=10)
            await player.set_filter(vibrato_filter)
            _set_player_filter_property(player, "vibrato")

        async def karaoke_apply(player: DefaultPlayer):
            """Applies a karaoke filter to the player."""
            karaoke_filter = Karaoke()
            karaoke_filter.update(level=0.6, mono_level=0.95)
            await player.set_filter(karaoke_filter)
            _set_player_filter_property(player, "karaoke")

        async def bass_boost_apply(player: DefaultPlayer):
            """Applies a bass boost filter to the player."""
            bb_filter = Equalizer()
            bb_filter.update(bands=[(0, 0.2), (1, 0.2), (2, 0.2)])
            await player.set_filter(bb_filter)
            _set_player_filter_property(player, "bass_boost")

        async def vapor_wave_apply(player: DefaultPlayer):
            """Applies a vaporwave filter to the player."""
            vw_filter = Equalizer()
            vw_filter.update(bands=[(1, 0.3), (0, 0.3)])
            timescale_filter = Timescale()
            timescale_filter.update(pitch=0.7)
            tremolo_filter = Tremolo()
            tremolo_filter.update(depth=0.3, frequency=14)
            await player.set_filter(vw_filter)
            await player.set_filter(timescale_filter)
            await player.set_filter(tremolo_filter)
            _set_player_filter_property(player, "vapor_wave")

        filters_to_register = [
            Filter("nightcore", "Nightcore", "Speeds up and raises the pitch of the song.", nightcore_apply),
            Filter("vapor_wave", "Vaporwave", "Time to chill out.", vapor_wave_apply),
            Filter("eight_d", "8D Audio", "I'm in your head.", eight_d_apply),
            Filter("vibrato", "Vibrato", "Adds a 'wobbly' effect.", vibrato_apply),
            Filter("low_pass", "Low Pass", "Club next door too loud?", low_pass_apply),
            Filter("karaoke", "Karaoke", "Having a karaoke night?", karaoke_apply),
            Filter("bass_boost", "Bass Boost", "Bass boosts the song.", bass_boost_apply),
        ]

        for filter_obj in filters_to_register:
            self._filters[filter_obj.name] = filter_obj

    def get_filter(self, name: str) -> Filter | None:
        """Get a filter by name."""
        return self._filters.get(name)

    def get_select_options(self, player: DefaultPlayer) -> list[discord.SelectOption]:
        """Get Discord SelectOptions for all filters."""
        return [filter_obj.to_select_option(player) for filter_obj in self._filters.values()]

    async def apply_filters(self, player: DefaultPlayer, filter_names: list[str]) -> list[str]:
        """Apply multiple filters to a player. Returns list of invalid filter names."""
        invalid_filters = []
        for filter_name in filter_names:
            filter_obj = self.get_filter(filter_name)
            if filter_obj:
                await filter_obj.apply(player)
            else:
                invalid_filters.append(filter_name)

        return invalid_filters

    def create_dropdown_view(self, service: "MusicService", interaction: discord.Interaction) -> "FilterDropdownView":
        """Create a dropdown view for filter selection."""
        return FilterDropdownView(self, service, interaction)


class FilterDropdownView(discord.ui.View):
    """A view that contains a dropdown menu for selecting audio filters."""

    DEFAULT_TIMEOUT = 60

    """A view that contains a dropdown menu for selecting audio filters."""

    def __init__(self, filter_mgr: FilterManager, service: "MusicService", interaction: discord.Interaction):
        super().__init__(timeout=FilterDropdownView.DEFAULT_TIMEOUT)
        self.filter_manager = filter_mgr
        self.service = service
        self.latest_interaction = interaction

        player = self.service.get_player_by_guild(interaction.guild.id)

        options = filter_mgr.get_select_options(player)
        dropdown = discord.ui.Select(
            placeholder="Choose some audio filters",
            min_values=0,
            max_values=len(options),
            options=options,
        )
        dropdown.callback = self._dropdown_callback
        self.add_item(dropdown)

        clear_button = discord.ui.Button(label="Clear Active Filters", style=discord.ButtonStyle.red)
        clear_button.callback = self._clear_button_callback
        self.add_item(clear_button)

    async def _dropdown_callback(self, interaction: discord.Interaction):
        """Handle dropdown selection."""
        dropdown = interaction.data["values"]
        await self.service.apply_filters(interaction.guild.id, interaction.user.id, dropdown)
        await self.latest_interaction.delete_original_response()

        message = "Removed all filters"
        if dropdown:
            selected_labels = []
            for filter_name in dropdown:
                filter_obj = self.filter_manager.get_filter(filter_name)
                if filter_obj:
                    selected_labels.append(filter_obj.label)
            message = f"Applied filters: {', '.join(selected_labels)}"

        await interaction.response.send_message(embed=interaction.client.create_embed("MOCBOT MUSIC", message, None))
        await asyncio.sleep(10)
        await interaction.delete_original_response()

    async def _clear_button_callback(self, interaction: discord.Interaction):
        """Handle clear button click."""
        await self.service.apply_filters(interaction.guild.id, interaction.user.id, [])
        await self.latest_interaction.delete_original_response()
        await interaction.response.send_message(
            embed=interaction.client.create_embed("MOCBOT MUSIC", "Cleared all filters", None)
        )
        await asyncio.sleep(10)
        await interaction.delete_original_response()

    async def on_timeout(self):
        """Handle view timeout."""
        await self.latest_interaction.delete_original_response()


filter_manager = FilterManager()
