import asyncio
import logging

import disnake
from disnake.ext import commands
from cog_config_provider import CogConfigProvider

logger = logging.getLogger(__name__)

DEFAULT_TEXT = "Click **Get Role** to receive the {role} role."


class GetRoleView(disnake.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @disnake.ui.button(
        label="Get Role",
        style=disnake.ButtonStyle.success,
        custom_id="rainbot:get_role:v1"
    )
    async def get_role_button(self, button, inter: disnake.MessageInteraction):
        await self.cog.handle_role_request(inter)


class GetRoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config_provider: CogConfigProvider):
        self.bot = bot
        self.guild_id = config_provider.guild_id
        self.config = config_provider.register(
            self, name="get_role",
            fields={"enabled": True, "post": None}
        )
        self._lock = asyncio.Lock()
        bot.add_view(GetRoleView(self))

    async def _check_admin(self, inter) -> bool:
        if (
            inter.guild_id != self.guild_id
            or not isinstance(inter.author, disnake.Member)
            or not inter.author.guild_permissions.manage_roles
        ):
            await inter.response.send_message(
                "Manage Roles permission is required.", ephemeral=True
            )
            return False
        return True

    @staticmethod
    def _can_assign(guild: disnake.Guild, role: disnake.Role) -> bool:
        me = guild.me
        return bool(
            me and me.guild_permissions.manage_roles
            and role < me.top_role
            and not role.managed
            and not role.is_default()
        )

    async def _fetch_message(self, post: dict):
        channel = self.bot.get_channel(post["channel_id"])
        if channel is None:
            channel = await self.bot.fetch_channel(post["channel_id"])
        return await channel.fetch_message(post["message_id"])

    async def _clear_deleted(self, channel_id: int, message_ids) -> None:
        async with self._lock:
            post = await self.config.post.get()
            if post and post["channel_id"] == channel_id and post["message_id"] in message_ids:
                await self.config.post.set(None)
                logger.info("[GetRole] Message deleted; post configuration cleared.")

    @commands.Cog.listener()
    async def on_ready(self):
        async with self._lock:
            post = await self.config.post.get()
            if not post:
                return

            try:
                await self._fetch_message(post)
            except disnake.NotFound:
                await self.config.post.set(None)
                logger.warning("[GetRole] Configured message no longer exists.")
            except (disnake.Forbidden, disnake.HTTPException):
                logger.warning("[GetRole] Could not verify message.", exc_info=True)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: disnake.RawMessageDeleteEvent):
        if payload.guild_id == self.guild_id:
            await self._clear_deleted(payload.channel_id, {payload.message_id})

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: disnake.RawBulkMessageDeleteEvent):
        if payload.guild_id == self.guild_id:
            await self._clear_deleted(payload.channel_id, payload.message_ids)

    async def handle_role_request(self, inter: disnake.MessageInteraction):
        await inter.response.defer(with_message=True, ephemeral=True)

        async def reply(text: str):
            await inter.edit_original_response(content=text)

        if inter.guild_id != self.guild_id or not isinstance(inter.author, disnake.Member):
            return await reply("This server is not configured.")

        if not await self.config.enabled.get():
            return await reply("Role assignment is currently disabled.")

        post = await self.config.post.get()
        if not post or (inter.channel_id, inter.message.id) != (
            post["channel_id"], post["message_id"]
        ):
            return await reply("This role assignment message is no longer active.")

        role = inter.guild.get_role(post["role_id"])
        if role is None:
            return await reply("The configured role no longer exists.")

        if role in inter.author.roles:
            return await reply("You already have this role.")

        if not self._can_assign(inter.guild, role):
            return await reply("I cannot assign this role. Contact an administrator.")

        try:
            await inter.author.add_roles(role, reason="Get Role button")
        except disnake.HTTPException:
            logger.exception("[GetRole] Failed to assign role %s.", role.id)
            return await reply("Failed to assign the role. Contact an administrator.")

        await reply(f"Role {role.mention} successfully assigned!")

    @commands.slash_command(
        name="get_role",
        description="Manage the Get Role system",
        default_member_permissions=disnake.Permissions(manage_roles=True)
    )
    async def get_role(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @get_role.sub_command(name="create", description="Create a Get Role message")
    async def create(
        self,
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role,
        text: str = commands.Param(
            default=DEFAULT_TEXT,
            description="Use {role} for the role mention"
        )
    ):
        if not await self._check_admin(inter):
            return

        if not self._can_assign(inter.guild, role):
            return await inter.response.send_message(
                "I cannot assign this role.", ephemeral=True
            )

        if inter.author.id != inter.guild.owner_id and role >= inter.author.top_role:
            return await inter.response.send_message(
                "This role is above your role hierarchy.", ephemeral=True
            )

        content = text.replace("{role}", role.mention)
        if len(content) > 2000:
            return await inter.response.send_message(
                "Message text is too long.", ephemeral=True
            )

        await inter.response.defer(ephemeral=True)

        async with self._lock:
            old_post = await self.config.post.get()

            try:
                message = await inter.channel.send(
                    content,
                    view=GetRoleView(self),
                    allowed_mentions=disnake.AllowedMentions.none()
                )
            except disnake.HTTPException:
                logger.exception("[GetRole] Failed to create message.")
                return await inter.followup.send(
                    "Failed to create the message.", ephemeral=True
                )

            try:
                await self.config.post.set({
                    "message_id": message.id,
                    "channel_id": message.channel.id,
                    "role_id": role.id,
                    "text": text
                })
            except Exception:
                logger.exception("[GetRole] Failed to save configuration.")
                try:
                    await message.delete()
                except disnake.HTTPException:
                    logger.warning("[GetRole] Could not remove orphaned message.")
                return await inter.followup.send(
                    "Failed to save the configuration.", ephemeral=True
                )

            if old_post:
                try:
                    old_message = await self._fetch_message(old_post)
                    await old_message.edit(view=None)
                except disnake.HTTPException:
                    logger.warning("[GetRole] Could not deactivate previous message.")

        await inter.followup.send(
            f"Get Role message created: {message.jump_url}", ephemeral=True
        )

    @get_role.sub_command(name="set_enabled", description="Enable or disable role assignment")
    async def set_enabled(
        self,
        inter: disnake.ApplicationCommandInteraction,
        enabled: bool
    ):
        if not await self._check_admin(inter):
            return

        await inter.response.defer(ephemeral=True)
        await self.config.enabled.set(enabled)
        await inter.followup.send(
            f"Role assignment {'enabled' if enabled else 'disabled'}.",
            ephemeral=True
        )