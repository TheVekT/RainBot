"""Event-driven Discord presence/voice statistics tracker."""

import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from itertools import islice

import disnake
from disnake.ext import commands, tasks

from .database.interface import AbstractPresenceRepository

logger = logging.getLogger(__name__)


def get_member_state(member: disnake.Member) -> str:
    """Resolve the combined presence and voice state (priority matters)."""
    if member.status is disnake.Status.offline:
        return "offline"
    voice = member.voice
    if not voice or not voice.channel:
        return "online"
    if voice.channel == member.guild.afk_channel:
        return "voice_afk"
    if len(voice.channel.members) == 1:
        return "voice_alone"
    if voice.self_deaf:
        return "voice_deaf"
    if voice.self_mute:
        return "voice_mute"
    return "voice_online"


class UserPresenceTracker:
    EVENTS = ("on_presence_update", "on_voice_state_update", "on_member_join", "on_member_remove")
    WRITE_BATCH_SIZE = 1000  # One batch every 5 seconds; statuses are coalesced per account.

    def __init__(self, bot: commands.Bot, guild_id: int, repo: AbstractPresenceRepository, retention_days: int = 365):
        self.bot, self.guild_id, self.repo = bot, guild_id, repo
        self.retention_days = retention_days
        self.guild: disnake.Guild | None = None
        self.user_states: dict[int, dict] = {}
        self._period_queue: deque[tuple] = deque()
        self._pending_status: dict[int, str] = {}
        self._pending_members: dict[int, disnake.Member] = {}
        self._pending_membership: dict[int, bool] = {}
        self._departed: set[int] = set()
        self._write_lock = asyncio.Lock()
        self._membership_lock = asyncio.Lock()
        self._ready = self._stopping = False
        self._skip_first_fixation = self._skip_first_daily = True

        for name in self.EVENTS:
            bot.add_listener(getattr(self, name))
        bot.add_listener(self._on_gateway_ready, "on_ready")
        self._init_task = asyncio.create_task(self.on_ready())

    def _tracked(self, member: disnake.Member) -> bool:
        return (member.guild.id == self.guild_id and
                (not member.bot or member.id == self.bot.user.id))

    @staticmethod
    def _snapshot(member: disnake.Member, at: datetime) -> tuple:
        voice = member.voice
        channel_id = voice.channel.id if voice and voice.channel else None
        return member, get_member_state(member), channel_id, at

    async def on_ready(self) -> None:
        """Load initial profiles, then seed every currently cached member's state."""
        try:
            await self.bot.wait_until_ready()
            if self._stopping:
                return
            self.guild = self.bot.get_guild(self.guild_id)
            if not self.guild:
                logger.error("[UserStats] Guild %s not found", self.guild_id)
                return

            # Keep membership events ordered after the snapshot and its DB writes.
            async with self._membership_lock:
                async with self._write_lock:
                    members, _ = await self._sync_profiles_locked()
                if self._stopping:
                    return

                now = datetime.now(timezone.utc)
                for member in members:
                    if self._tracked(member):
                        _, state, channel_id, _ = self._snapshot(member, now)
                        self.user_states[member.id] = dict(state=state, channel_id=channel_id, start_time=now)
                        self._pending_status[member.id] = state
                self._ready = True
            for loop in (self.write_queue, self.periodic_state_fixation, self.daily_profile_sync,
                         self.clean_old_stats, self.compress_stats):
                loop.start()
            logger.info("[UserStats] Initialized %s members in %s", len(self.user_states), self.guild.name)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[UserStats] Initialization failed")

    async def _on_gateway_ready(self) -> None:
        """Reconcile cached states after a Gateway reconnect (missed events are possible)."""
        if self._ready and not self._stopping and self.guild:
            try:
                await self._sync_profiles()
                await asyncio.gather(*(self.update_user_state(m) for m in self.guild.members if self._tracked(m)))
            except Exception:
                logger.exception("[UserStats] Reconnect synchronization failed")

    async def on_presence_update(self, before: disnake.Member, after: disnake.Member) -> None:
        if self._ready and not self._stopping and self._tracked(after):
            await self.update_user_state(after)

    async def on_voice_state_update(self, member: disnake.Member,
                                    before: disnake.VoiceState, after: disnake.VoiceState) -> None:
        if not self._ready or self._stopping or member.guild.id != self.guild_id:
            return
        # Joining/leaving a channel also changes voice_alone for its other members.
        affected = {member.id: member}
        if before.channel != after.channel:
            for channel in (before.channel, after.channel):
                if channel:
                    affected.update((m.id, m) for m in channel.members)

        now = datetime.now(timezone.utc)
        snapshots = [self._snapshot(m, now) for m in affected.values() if self._tracked(m)]
        await asyncio.gather(*(self._apply_state(*snapshot) for snapshot in snapshots))

    async def on_member_join(self, member: disnake.Member) -> None:
        if self._stopping or not self._tracked(member):
            return
        at = datetime.now(timezone.utc)
        if not self._ready:
            await asyncio.shield(self._init_task)
        async with self._membership_lock:
            if not self._ready or self._stopping:
                return
            # Upsert even for a returning member, then apply the latest membership
            # after the account exists. A rapid join/leave is coalesced safely.
            self._pending_members[member.id] = member
            self._pending_membership[member.id] = True
            self._departed.discard(member.id)
            await self._apply_state(*self._snapshot(member, at))

    async def on_member_remove(self, member: disnake.Member) -> None:
        if self._stopping or not self._tracked(member):
            return
        now = datetime.now(timezone.utc)
        if not self._ready:
            await asyncio.shield(self._init_task)
        async with self._membership_lock:
            if not self._ready or self._stopping:
                return
            info = self.user_states.pop(member.id, None)
            if info:
                self.record_state_period(member.id, info["state"], info["start_time"], now, info["channel_id"])
            self._departed.add(member.id)
            self._pending_membership[member.id] = False

        if member.voice and member.voice.channel:
            peers = [m for m in member.voice.channel.members if m.id != member.id and self._tracked(m)]
            await asyncio.gather(*(self.update_user_state(m) for m in peers))

    async def update_user_state(self, member: disnake.Member) -> None:
        if self._ready and not self._stopping and self._tracked(member):
            await self._apply_state(*self._snapshot(member, datetime.now(timezone.utc)))

    async def _apply_state(self, member: disnake.Member, state: str,
                           channel_id: int | None, at: datetime) -> None:
        if self._stopping or member.id in self._departed:
            return
        old = self.user_states.get(member.id)
        if old and (old["state"], old["channel_id"]) == (state, channel_id):
            return
        if old:
            at = max(at, old["start_time"])
            self.record_state_period(member.id, old["state"], old["start_time"], at, old["channel_id"])
        else:
            self._pending_members[member.id] = member  # Create a new FK account in the writer.
        self.user_states[member.id] = dict(state=state, channel_id=channel_id, start_time=at)
        self._pending_status[member.id] = state  # Repeated mute/unmute overwrites the pending DB status.

    def record_state_period(self, account_id: int, state: str, start_time: datetime,
                            end_time: datetime, channel_id: int | None = None) -> None:
        if start_time >= end_time:
            return
        self.record_period_split(account_id, state, start_time, end_time, channel_id)

    def _queue_period(self, period: tuple) -> None:
        # Do not modify an entry a concurrent writer may already have copied.
        # Older periods are consolidated by compress_records instead.
        self._period_queue.append(period)

    def record_period_split(self, account_id: int, state: str, dt_start: datetime,
                            dt_end: datetime, channel_id: int | None = None) -> None:
        while dt_start.date() < dt_end.date():
            midnight = datetime.combine(dt_start.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
            self._queue_period((account_id, state, dt_start, midnight, channel_id))
            dt_start = midnight
        if dt_start < dt_end:
            self._queue_period((account_id, state, dt_start, dt_end, channel_id))

    async def _sync_profile(self, member: disnake.Member, state: str) -> None:
        if await self.repo.is_account_exist(member.id):
            await self.repo.update_account_status(member.id, state)
        else:
            avatar = str(member.display_avatar.url) if member.display_avatar else ""
            await self.repo.create_account(member.id, member.name, member.display_name, avatar, state)

    def _flush_one(self, account_id: int, now: datetime) -> None:
        info = self.user_states.get(account_id)
        if info and info["start_time"] < now:
            self.record_state_period(account_id, info["state"], info["start_time"], now, info["channel_id"])
            info["start_time"] = now

    async def _drain_queue(self, limit: int | None = WRITE_BATCH_SIZE) -> None:
        """Single writer; failures leave untouched entries queued for retry."""
        async with self._write_lock:
            try:
                for uid, member in list(self._pending_members.items())[:limit]:
                    status = self._pending_status.get(uid, get_member_state(member))
                    await self._sync_profile(member, status)
                    if self._pending_members.get(uid) is member:
                        self._pending_members.pop(uid, None)
                    if self._pending_status.get(uid) == status:
                        self._pending_status.pop(uid, None)

                batch = list(islice(self._period_queue, limit or self.WRITE_BATCH_SIZE))
                # A batch may contain a newcomer beyond the pending-member slice.
                for uid in {period[0] for period in batch}:
                    member = self._pending_members.get(uid)
                    if member:
                        status = self._pending_status.get(uid, get_member_state(member))
                        await self._sync_profile(member, status)
                        if self._pending_members.get(uid) is member:
                            self._pending_members.pop(uid, None)
                        if self._pending_status.get(uid) == status:
                            self._pending_status.pop(uid, None)
                for channel_id in {period[4] for period in batch if period[4] is not None}:
                    if not await self.repo.is_channel_exist(channel_id):
                        channel = self.guild.get_channel(channel_id) if self.guild else None
                        name = channel.name if channel else f"Unknown Channel {channel_id}"
                        await self.repo.create_channel(channel_id, name, channel is not None)
                if batch:
                    await self.repo.bulk_save_periods(batch)
                    for _ in batch:
                        self._period_queue.popleft()  # Remove only after the entire batch succeeds.

                for uid, is_member in list(self._pending_membership.items())[:limit]:
                    if uid in self._pending_members:
                        continue
                    await self.repo.set_account_membership(uid, is_member)
                    if self._pending_membership.get(uid) == is_member:
                        self._pending_membership.pop(uid, None)

                for uid, status in list(self._pending_status.items())[:limit]:
                    if uid in self._pending_members:
                        continue
                    await self.repo.update_account_status(uid, status)
                    if self._pending_status.get(uid) == status:
                        self._pending_status.pop(uid, None)
            except Exception:
                logger.exception("[UserStats] Queue write failed; pending entries will be retried")

    @tasks.loop(seconds=5)
    async def write_queue(self) -> None:
        await self._drain_queue()

    @tasks.loop(minutes=10)
    async def periodic_state_fixation(self) -> None:
        if self._skip_first_fixation:
            self._skip_first_fixation = False
            return
        now = datetime.now(timezone.utc)
        for uid in list(self.user_states):
            self._flush_one(uid, now)

    async def _sync_profiles(self) -> None:
        async with self._membership_lock:
            async with self._write_lock:
                guild = self.bot.get_guild(self.guild_id)
                if guild is None:
                    raise RuntimeError("Guild is not present in the current Discord session")
                self.guild = guild
                await self._sync_profiles_locked()

    async def _sync_profiles_locked(self) -> tuple[list[disnake.Member], bool]:
        # A partial member cache must never be interpreted as people leaving.
        # chunk() explicitly requests the full guild member list.
        if self.guild.unavailable:
            raise RuntimeError("Guild is unavailable; profile synchronization skipped")
        try:
            chunk_members = await asyncio.wait_for(self.guild.chunk(cache=True), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("[UserStats] Timed out loading guild members; membership reconciliation skipped")
            chunk_members = None
        if self.guild.unavailable:
            raise RuntimeError("Guild became unavailable during synchronization")
        # chunk() member objects lack presence data; use the cache for statuses,
        # but use the returned IDs for membership (the cache may contain stale entries).
        members = ([self.guild.get_member(m.id) or m for m in chunk_members]
                   if chunk_members is not None else list(self.guild.members))
        complete = (chunk_members is not None and self.guild.member_count is not None and
                    len({member.id for member in chunk_members}) == self.guild.member_count)
        if not complete:
            logger.warning("[UserStats] Guild member cache is incomplete; skipping membership reconciliation")

        channels = [(ch.id, ch.name, True) for ch in self.guild.voice_channels]
        await self.repo.sync_channels(channels)

        accounts = []
        for member in members:
            if not self._tracked(member):
                continue
            avatar = str(member.display_avatar.url) if member.display_avatar else ""
            accounts.append((member.id, member.name, member.display_name, avatar, get_member_state(member)))
        if accounts:
            await self.repo.bulk_upsert_accounts(accounts)
        if complete:
            tracked_ids = {account[0] for account in accounts}
            await self.repo.reconcile_members(list(tracked_ids))
            # Pending lifecycle writes predate this authoritative snapshot.
            # Preserve them for newly-created accounts, but use the snapshot's
            # membership so they cannot later undo reconciliation.
            for uid in self._pending_membership:
                self._pending_membership[uid] = uid in tracked_ids
            if self._ready:
                now = datetime.now(timezone.utc)
                for uid in set(self.user_states) - tracked_ids:
                    # The departure was missed, so its time is unknown. Discard
                    # the unflushed tail rather than fabricate activity up to now.
                    self.user_states.pop(uid)
                    self._departed.add(uid)
                for member in members:
                    if self._tracked(member):
                        self._departed.discard(member.id)
                        if member.id not in self.user_states:
                            await self._apply_state(*self._snapshot(member, now))
        logger.info("[UserStats] Synced %s accounts and %s voice channels", len(accounts), len(channels))
        return members, complete

    @tasks.loop(hours=24)
    async def daily_profile_sync(self) -> None:
        if self._skip_first_daily:
            self._skip_first_daily = False
            return
        try:
            await self._sync_profiles()
        except Exception:
            logger.exception("[UserStats] Daily profile sync failed")

    @tasks.loop(hours=1)
    async def clean_old_stats(self) -> None:
        try:
            await self.repo.clean_old_records(datetime.now(timezone.utc) - timedelta(days=self.retention_days))
        except Exception:
            logger.exception("[UserStats] Cleanup failed")

    @tasks.loop(minutes=10)
    async def compress_stats(self) -> None:
        try:
            await self.repo.compress_records(datetime.now(timezone.utc) - timedelta(days=2))
        except Exception:
            logger.exception("[UserStats] Compression failed")

    async def stop(self) -> None:
        self._stopping = True
        self._ready = False
        for name in self.EVENTS:
            self.bot.remove_listener(getattr(self, name))
        self.bot.remove_listener(self._on_gateway_ready, "on_ready")

        loops = (self.write_queue, self.periodic_state_fixation, self.daily_profile_sync,
                 self.clean_old_stats, self.compress_stats)
        running = [loop.get_task() for loop in loops if loop.is_running()]
        for loop in loops:
            loop.cancel()
        self._init_task.cancel()
        await asyncio.gather(self._init_task, *(task for task in running if task), return_exceptions=True)

        now = datetime.now(timezone.utc)
        for uid in list(self.user_states):
            self._flush_one(uid, now)

        async def flush_remaining():
            while self._period_queue or self._pending_status or self._pending_members or self._pending_membership:
                old_count = len(self._period_queue) + len(self._pending_status) + len(self._pending_members) + len(self._pending_membership)
                await self._drain_queue()
                new_count = len(self._period_queue) + len(self._pending_status) + len(self._pending_members) + len(self._pending_membership)
                if new_count >= old_count:  # Database error; avoid retrying endlessly on shutdown.
                    break

        try:
            await asyncio.wait_for(flush_remaining(), timeout=6)
        except asyncio.TimeoutError:
            logger.error("[UserStats] Shutdown queue flush timed out")
        if self._period_queue or self._pending_status or self._pending_members or self._pending_membership:
            logger.error("[UserStats] Unwritten data: %d periods, %d statuses, %d accounts, %d memberships",
                         len(self._period_queue), len(self._pending_status), len(self._pending_members), len(self._pending_membership))
        self.user_states.clear()
        logger.info("[UserStats] Tracker stopped")
