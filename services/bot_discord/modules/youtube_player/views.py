"""Discord UI views (button panels) for the YouTube music player.

Each view is a self-contained ``disnake.ui.View`` subclass that delegates
user actions back to the ``YouTubePlayer`` instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import disnake

if TYPE_CHECKING:
    from modules.youtube_player.player import GuildMusicState, YouTubePlayer


# ── Volume panel ─────────────────────────────────────────────────────

class VolumeView(disnake.ui.View):
    """± Volume buttons with a *Back* button to return to options."""

    def __init__(self, player: YouTubePlayer, guild_id: int) -> None:
        super().__init__(timeout=None)
        self.player = player
        self.guild_id = guild_id

    @disnake.ui.button(label="- Vol", style=disnake.ButtonStyle.red, row=0)
    async def vol_down(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction,
    ) -> None:
        await interaction.response.defer()
        await self.player.change_volume(self.guild_id, -0.25)

    @disnake.ui.button(label="+ Vol", style=disnake.ButtonStyle.green, row=0)
    async def vol_up(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction,
    ) -> None:
        await interaction.response.defer()
        await self.player.change_volume(self.guild_id, 0.25)

    @disnake.ui.button(label="Back", style=disnake.ButtonStyle.secondary, row=1)
    async def back(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction,
    ) -> None:
        await interaction.response.defer()
        await self.player.update_player_message(self.guild_id, view_type="options")


# ── Options panel (repeat, volume settings) ──────────────────────────

class OptionsView(disnake.ui.View):
    """Repeat toggle and volume-settings entry point."""

    def __init__(
        self,
        player: YouTubePlayer,
        guild_id: int,
        current_state: GuildMusicState,
    ) -> None:
        super().__init__(timeout=None)
        self.player = player
        self.guild_id = guild_id

        style = (
            disnake.ButtonStyle.green
            if current_state.repeat
            else disnake.ButtonStyle.gray
        )
        label = "Repeat: ON" if current_state.repeat else "Repeat: OFF"
        self.add_item(
            disnake.ui.Button(label=label, style=style, custom_id="opt_repeat", row=0),
        )
        self.add_item(
            disnake.ui.Button(
                label="Volume Settings",
                style=disnake.ButtonStyle.blurple,
                custom_id="opt_volume",
                row=0,
            ),
        )
        self.add_item(
            disnake.ui.Button(
                label="Back",
                style=disnake.ButtonStyle.secondary,
                custom_id="opt_back",
                row=1,
            ),
        )

    async def interaction_check(
        self, interaction: disnake.MessageInteraction,
    ) -> bool:
        cid = interaction.data.custom_id
        if cid == "opt_repeat":
            await interaction.response.defer()
            await self.player.toggle_repeat(self.guild_id)
        elif cid == "opt_volume":
            await interaction.response.defer()
            await self.player.update_player_message(self.guild_id, view_type="volume")
        elif cid == "opt_back":
            await interaction.response.defer()
            await self.player.update_player_message(self.guild_id, view_type="main")
        return True


# ── Effects panel (bass boost, speed) ────────────────────────────────

class EffectsView(disnake.ui.View):
    """Bass boost and speed effect toggles."""

    def __init__(
        self,
        player: YouTubePlayer,
        guild_id: int,
        current_state: GuildMusicState,
    ) -> None:
        super().__init__(timeout=None)
        self.player = player
        self.guild_id = guild_id

        # Bass boost button.
        style_bb = (
            disnake.ButtonStyle.green
            if current_state.bass_boost
            else disnake.ButtonStyle.gray
        )
        label_bb = "Bass: ON" if current_state.bass_boost else "Bass: OFF"
        self.add_item(
            disnake.ui.Button(
                label=label_bb, style=style_bb, custom_id="effect_bass", row=0,
            ),
        )

        # Slow (0.5×) button.
        style_slow = (
            disnake.ButtonStyle.green
            if current_state.slowed
            else disnake.ButtonStyle.gray
        )
        self.add_item(
            disnake.ui.Button(
                label="Slow (0.5x)", style=style_slow, custom_id="effect_slow", row=1,
            ),
        )

        # Fast (2.0×) button.
        style_fast = (
            disnake.ButtonStyle.green
            if current_state.sped_up
            else disnake.ButtonStyle.gray
        )
        self.add_item(
            disnake.ui.Button(
                label="Fast (2.0x)", style=style_fast, custom_id="effect_fast", row=1,
            ),
        )

        self.add_item(
            disnake.ui.Button(
                label="Back",
                style=disnake.ButtonStyle.secondary,
                custom_id="effect_back",
                row=2,
            ),
        )

    async def interaction_check(
        self, interaction: disnake.MessageInteraction,
    ) -> bool:
        cid = interaction.data.custom_id
        if cid == "effect_bass":
            await interaction.response.defer()
            await self.player.toggle_effect(self.guild_id, "bass")
        elif cid == "effect_slow":
            await interaction.response.defer()
            await self.player.toggle_effect(self.guild_id, "slow")
        elif cid == "effect_fast":
            await interaction.response.defer()
            await self.player.toggle_effect(self.guild_id, "fast")
        elif cid == "effect_back":
            await interaction.response.defer()
            await self.player.update_player_message(self.guild_id, view_type="main")
        return True


# ── Main player controls ─────────────────────────────────────────────

class MusicView(disnake.ui.View):
    """Primary player controls: pause/resume, stop, options, effects."""

    def __init__(self, player: YouTubePlayer, guild_id: int) -> None:
        super().__init__(timeout=None)
        self.player = player
        self.guild_id = guild_id

    @disnake.ui.button(
        label="Pause/Resume",
        style=disnake.ButtonStyle.blurple,
        custom_id="music_pause_resume",
        row=0,
    )
    async def pause_resume(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction,
    ) -> None:
        await interaction.response.defer()
        await self.player.toggle_pause(interaction.guild.id, interaction)

    @disnake.ui.button(
        label="Stop",
        style=disnake.ButtonStyle.red,
        custom_id="music_stop",
        row=0,
    )
    async def stop(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction,
    ) -> None:
        await interaction.response.defer()
        await self.player.stop(interaction.guild.id, interaction)

    @disnake.ui.button(
        label="Options",
        style=disnake.ButtonStyle.secondary,
        custom_id="music_options",
        row=0,
    )
    async def options(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction,
    ) -> None:
        await interaction.response.defer()
        await self.player.update_player_message(
            interaction.guild.id, view_type="options",
        )

    @disnake.ui.button(
        label="Effects",
        style=disnake.ButtonStyle.secondary,
        custom_id="music_effects",
        row=0,
    )
    async def effects(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction,
    ) -> None:
        await interaction.response.defer()
        await self.player.update_player_message(
            interaction.guild.id, view_type="effects",
        )
