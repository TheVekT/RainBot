import asyncio
import logging
import time

import disnake
from disnake.ext import commands
from cog_config_provider import CogConfigProvider

logger = logging.getLogger(__name__)

MOVE_DELAY = 0.25
MAX_ROUNDS = 10


class WakeError(Exception):
    pass


class WakeCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config_provider: CogConfigProvider):
        self.bot = bot
        self.guild_id = config_provider.guild_id
        self.config = config_provider.register(
            self, name="wake",
            fields={
                "cooldown_seconds": 1.0,
                "rounds": 2,
                "tech_channels": None
            }
        )

        self._next_allowed: dict[int, float] = {}
        self._active_channels: set[int] = set()

    @staticmethod
    def _require(condition: bool, message: str):
        if not condition:
            raise WakeError(message)

    async def _check_admin(self, inter: disnake.ApplicationCommandInteraction) -> bool:
        if (
            inter.guild_id != self.guild_id
            or not isinstance(inter.author, disnake.Member)
            or not inter.author.guild_permissions.administrator
        ):
            await inter.response.send_message(
                "Administrator permission is required.", ephemeral=True
            )
            return False
        return True

    @commands.user_command(name="Wake Up")
    async def wake_up(self, inter: disnake.UserCommandInteraction, target: disnake.User):
        await inter.response.defer(ephemeral=True)

        try:
            await self._execute(inter, target)
            await inter.edit_original_response(
                content=f"Successfully woke up {target.mention}!"
            )
        except WakeError as exc:
            logger.info("[Wake] Rejected: %s", exc)
            await inter.edit_original_response(content=f"Wake Up unavailable: {exc}")
        except Exception:
            logger.exception("[Wake] Unexpected error.")
            await inter.edit_original_response(content="Wake Up failed.")

    async def _execute(self, inter: disnake.UserCommandInteraction, target: disnake.User):
        guild = inter.guild
        self._require(guild is not None and guild.id == self.guild_id, "Invalid guild")

        author = inter.author
        member = guild.get_member(target.id)

        self._require(isinstance(author, disnake.Member), "Invalid author")
        self._require(member is not None, "Target not found")
        self._require(member.id != author.id and not member.bot, "Invalid target")

        source = author.voice.channel if author.voice else None
        voice = member.voice

        self._require(isinstance(source, disnake.VoiceChannel), "Author not in voice")
        self._require(voice is not None and voice.channel == source, "Different voice channels")
        self._require(not voice.self_stream, "Target is screen sharing")

        config = await self.config.tech_channels.get()
        self._require(isinstance(config, dict), "Technical channels not configured")

        first = guild.get_channel(config.get("first_id"))
        second = guild.get_channel(config.get("second_id"))

        self._require(
            isinstance(first, disnake.VoiceChannel)
            and isinstance(second, disnake.VoiceChannel),
            "Technical channels missing"
        )
        self._require(len({source.id, first.id, second.id}) == 3, "Invalid channel configuration")

        me = guild.me
        self._require(me is not None, "Bot member unavailable")
        self._require(
            all(ch.permissions_for(me).move_members for ch in (source, first, second))
            and all(ch.permissions_for(me).connect for ch in (first, second)),
            "Missing voice permissions"
        )

        cooldown = max(1.0, float(await self.config.cooldown_seconds.get()))
        rounds = max(1, min(MAX_ROUNDS, int(await self.config.rounds.get())))
        now = time.monotonic()

        self._require(source.id not in self._active_channels, "Operation already running")
        self._require(now >= self._next_allowed.get(source.id, 0), "Channel cooldown active")

        self._active_channels.add(source.id)
        self._next_allowed[source.id] = now + cooldown
        moved = False

        try:
            for _ in range(rounds):
                for channel in (first, second):
                    state = member.voice
                    self._require(
                        state is not None
                        and state.channel is not None
                        and state.channel.id in {source.id, first.id, second.id},
                        "Target left the operation channels"
                    )

                    await member.move_to(channel, reason=f"Wake Up by {author}")
                    moved = True
                    await asyncio.sleep(MOVE_DELAY)

            logger.info("[Wake] Completed for %s by %s.", member.name, author.name)

        finally:
            if moved:
                state = member.voice
                if (
                    state is not None
                    and state.channel is not None
                    and state.channel.id in {source.id, first.id, second.id}
                ):
                    try:
                        await member.move_to(source, reason="Wake Up: restore channel")
                    except (disnake.Forbidden, disnake.HTTPException):
                        logger.exception("[Wake] Failed to restore member %s.", member.id)
                else:
                    logger.warning("[Wake] Member %s left; restoration skipped.", member.id)

            self._active_channels.discard(source.id)

    @commands.slash_command(
        name="wake",
        description="Configure Wake Up",
        default_member_permissions=disnake.Permissions(administrator=True)
    )
    async def wake(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @wake.sub_command(name="configure", description="Configure cooldown and repetitions")
    async def configure(
        self,
        inter: disnake.ApplicationCommandInteraction,
        cooldown_seconds: float = commands.Param(ge=1.0, le=120.0),
        rounds: int = commands.Param(ge=1, le=MAX_ROUNDS)
    ):
        if not await self._check_admin(inter):
            return

        await inter.response.defer(ephemeral=True)
        await self.config.cooldown_seconds.set(cooldown_seconds)
        await self.config.rounds.set(rounds)

        await inter.followup.send(
            f"Cooldown: **{cooldown_seconds}s**\nRepetitions: **{rounds}**",
            ephemeral=True
        )

    @wake.sub_command(name="channels", description="Set technical voice channels")
    async def channels(
        self,
        inter: disnake.ApplicationCommandInteraction,
        first: disnake.VoiceChannel,
        second: disnake.VoiceChannel
    ):
        if not await self._check_admin(inter):
            return

        if first.id == second.id:
            await inter.response.send_message(
                "Select two different channels.", ephemeral=True
            )
            return

        await inter.response.defer(ephemeral=True)
        await self.config.tech_channels.set({
            "first_id": first.id,
            "second_id": second.id
        })

        await inter.followup.send(
            f"Technical channels: {first.mention} → {second.mention}",
            ephemeral=True
        )