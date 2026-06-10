import disnake
from disnake.ext import tasks, commands
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from .database.interface import AbstractPresenceRepository

logger = logging.getLogger(__name__)

def get_member_state(member: disnake.Member) -> str:
    """
    Determines the current voice or online presence state of a guild member.
    """
    if member.status is disnake.Status.offline:
        return "offline"
    elif member.voice:
        if member.voice.channel == member.guild.afk_channel:
            return "voice_afk"
        elif len(member.voice.channel.members) == 1:
            return "voice_alone"
        elif member.voice.self_deaf:
            return "voice_deaf"
        elif member.voice.self_mute:
            return "voice_mute"
        else:
            return "voice_online"
    else:
        return "online"


class UserPresenceTracker:
    """
    Tracks and records the presence status of Discord guild members over time.
    Separates high-frequency interval updates from background profile management.
    """
    def __init__(self, bot: commands.Bot, guild_id: int, repo: AbstractPresenceRepository, retention_days: int = 365):
        self.bot = bot
        self.guild_id = guild_id
        self.repo = repo
        self.retention_days = retention_days
        self.user_states = {}  # {account_id: {"state": str, "channel_id": int | None, "start_time": datetime(UTC)}}
        self.guild = None

        self._start()

    def _start(self) -> None:
        asyncio.create_task(self.on_ready())
        self.periodic_state_fixation.start()

    async def on_ready(self) -> None:
        await self.bot.wait_until_ready()
        self.guild = self.bot.get_guild(self.guild_id)
        
        if not self.guild:
            logger.warning(f"[UserStats] Guild with ID {self.guild_id} not found.")
            return
        
        logger.info(f"[UserStats] Tracker initialized for guild: {self.guild.name}")
        self.periodic_stats_update.start()
        self.clean_old_stats.start()
        self.compress_stats.start()
        self.daily_profile_sync.start()

    async def update_user_state(self, member: disnake.Member) -> None:
        if member.bot and member.id != self.bot.user.id:
            return

        account_id = member.id
        current_state = get_member_state(member)
        current_channel_id = member.voice.channel.id if member.voice and member.voice.channel else None
        now_utc = datetime.now(timezone.utc)
        
        previous_state_info = self.user_states.get(account_id)
        
        if previous_state_info:
            previous_state = previous_state_info["state"]
            previous_channel_id = previous_state_info["channel_id"]
            start_time = previous_state_info["start_time"]
        else:
            previous_state = None
            previous_channel_id = None
            start_time = now_utc
            
        if current_state != previous_state or current_channel_id != previous_channel_id:
            if previous_state is not None:
                await self.record_state_period(member, previous_state, start_time, now_utc, previous_channel_id)
            self.user_states[account_id] = {"state": current_state, "channel_id": current_channel_id, "start_time": now_utc}

    async def record_state_period(self, member: disnake.Member, state: str, start_time: datetime, end_time: datetime, channel_id: int | None = None) -> None:
        account_id = member.id
        
        # Ensure channel entity is verified in DB tracking layer before presence insertion
        if channel_id and not await self.repo.is_channel_exist(channel_id):
            ch_obj = self.guild.get_channel(channel_id) if self.guild else None
            ch_name = ch_obj.name if ch_obj else f"Unknown Channel {channel_id}"
            await self.repo.create_channel(channel_id, ch_name, is_active=True)

        # 1. Immediate interval insert to prevent gaps or polling lag
        if start_time.date() != end_time.date():
            await self.record_period_split(account_id, state, start_time, end_time, channel_id)
        else:
            await self.repo.save_period(account_id, state, start_time, end_time, channel_id)
        
        # 2. Fire and forget background synchronization for profile accounts table
        asyncio.create_task(self._sync_profile_background(member))

    async def record_period_split(self, account_id: int, state: str, dt_start: datetime, dt_end: datetime, channel_id: int | None = None) -> None:
        while dt_start.date() < dt_end.date():
            end_of_day = datetime.combine(dt_start.date(), datetime.max.time(), tzinfo=timezone.utc)
            if end_of_day >= dt_start:
                await self.repo.save_period(account_id, state, dt_start, end_of_day, channel_id)
            dt_start = datetime.combine(dt_start.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        
        if dt_start < dt_end:
            await self.repo.save_period(account_id, state, dt_start, dt_end, channel_id)

    async def _sync_profile_background(self, member: disnake.Member) -> None:
        """Background profile execution task ensuring existence before tracking status changes."""
        try:
            account_id = member.id
            current_status = get_member_state(member)
            
            exists = await self.repo.is_account_exist(account_id)
            if not exists:
                avatar_url = str(member.display_avatar.url) if member.display_avatar else ""
                await self.repo.create_account(
                    account_id=account_id,
                    username=member.name,          # Передаем глобальный логин
                    nickname=member.display_name,  # Серверное имя
                    avatar_url=avatar_url,
                    current_status=current_status
                )
            else:
                await self.repo.update_account_status(account_id, current_status)
        except Exception as e:
            logger.error(f"Error in background profile sync for user {member.id}: {e}")

    @tasks.loop(seconds=3)
    async def periodic_stats_update(self) -> None:
        if not self.guild:
            return
        tasks_list = [self.update_user_state(member) for member in self.guild.members]
        await asyncio.gather(*tasks_list, return_exceptions=True)

    @tasks.loop(minutes=10)
    async def periodic_state_fixation(self) -> None:
        now_utc = datetime.now(timezone.utc)
        account_ids = list(self.user_states.keys())
        
        for account_id in account_ids:
            state_info = self.user_states.get(account_id)
            if not state_info:
                continue
            
            last_time = state_info["start_time"]
            state = state_info["state"]
            channel_id = state_info["channel_id"]
            
            if now_utc > last_time:
                member = self.guild.get_member(account_id) if self.guild else None
                if member:
                    await self.record_state_period(member, state, last_time, now_utc, channel_id)
                else:
                    if channel_id and not await self.repo.is_channel_exist(channel_id):
                        ch_obj = self.guild.get_channel(channel_id) if self.guild else None
                        ch_name = ch_obj.name if ch_obj else f"Unknown Channel {channel_id}"
                        await self.repo.create_channel(channel_id, ch_name, is_active=True)
                        
                    if last_time.date() != now_utc.date():
                        await self.record_period_split(account_id, state, last_time, now_utc, channel_id)
                    else:
                        await self.repo.save_period(account_id, state, last_time, now_utc, channel_id)
                
                # Check if state didn't change while we were awaiting
                current_info = self.user_states.get(account_id)
                if (current_info and 
                    current_info["start_time"] == last_time and 
                    current_info["state"] == state and 
                    current_info["channel_id"] == channel_id):
                    self.user_states[account_id]["start_time"] = now_utc

    @tasks.loop(hours=24)
    async def daily_profile_sync(self) -> None:
        """Scheduled mass synchronization to update avatar URLs and nicknames from Discord."""
        if not self.guild:
            return
        logger.info("[UserStats] Executing daily full profile synchronization...")
        try:
            # Sync channels topology structure
            batch_channels = []
            for channel in self.guild.voice_channels:
                batch_channels.append((channel.id, channel.name, True))
            if batch_channels:
                await self.repo.bulk_upsert_channels(batch_channels)

            # Sync user configurations profiles
            batch_data = []
            for member in self.guild.members:
                if member.bot and member.id != self.bot.user.id:
                    continue
                avatar_url = str(member.display_avatar.url) if member.display_avatar else ""
                current_status = get_member_state(member)
                batch_data.append((
                    member.id,
                    member.name,
                    member.display_name,
                    avatar_url,
                    current_status
                ))
            if batch_data:
                await self.repo.bulk_upsert_accounts(batch_data)
                logger.info(f"[UserStats] Successfully synced {len(batch_data)} profiles and {len(batch_channels)} voice channels.")
        except Exception as e:
            logger.error(f"Error in daily profile sync: {e}")

    @tasks.loop(hours=1)
    async def clean_old_stats(self) -> None:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        try:
            await self.repo.clean_old_records(cutoff_date)
        except Exception as e:
            logger.error(f"Error cleaning old stats: {e}")

    @tasks.loop(minutes=10)
    async def compress_stats(self) -> None:
        since_date = datetime.now(timezone.utc) - timedelta(days=2)
        try:
            await self.repo.compress_records(since_date)
        except Exception as e:
            logger.error(f"Error in compress_stats: {e}")

    async def stop(self) -> None:
        now_utc = datetime.now(timezone.utc)
        tasks_to_save = []
        user_states_copy = list(self.user_states.items())
        
        for account_id, state_info in user_states_copy:
            member = self.guild.get_member(account_id) if self.guild else None
            last_time = state_info['start_time']
            state = state_info['state']
            channel_id = state_info['channel_id']
            
            if now_utc > last_time:
                if member:
                    tasks_to_save.append(
                        self.record_state_period(member, state, last_time, now_utc, channel_id)
                    )
                else:
                    async def save_fallback(acc_id=account_id, st=state, lt=last_time, nt=now_utc, ch_id=channel_id):
                        if ch_id and not await self.repo.is_channel_exist(ch_id):
                            ch_obj = self.guild.get_channel(ch_id) if self.guild else None
                            ch_name = ch_obj.name if ch_obj else f"Unknown Channel {ch_id}"
                            await self.repo.create_channel(ch_id, ch_name, is_active=True)
                            
                        if lt.date() != nt.date():
                            await self.record_period_split(acc_id, st, lt, nt, ch_id)
                        else:
                            await self.repo.save_period(acc_id, st, lt, nt, ch_id)
                    
                    tasks_to_save.append(save_fallback())
            
        if tasks_to_save:
            await asyncio.gather(*tasks_to_save, return_exceptions=True)
            
        self.periodic_stats_update.cancel()
        self.clean_old_stats.cancel()
        self.compress_stats.cancel()
        self.periodic_state_fixation.cancel()
        self.daily_profile_sync.cancel()
        self.user_states.clear()
        logger.info("[UserStats] Tracker stopped.")