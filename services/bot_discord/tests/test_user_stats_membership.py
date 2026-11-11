import asyncio
import sys
import unittest
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import disnake
from modules.users_stats.stats import UserPresenceTracker


class Repository:
    def __init__(self):
        self.accounts = {}
        self.channels = {}
        self.periods = []
        self.sync_entered = None
        self.sync_release = None
        self.save_entered = None
        self.save_release = None
        self.membership_entered = None
        self.membership_release = None

    async def is_account_exist(self, uid):
        return uid in self.accounts

    async def create_account(self, uid, username, nickname, avatar, status):
        self.accounts[uid] = [status, True]

    async def update_account_status(self, uid, status):
        self.accounts[uid][0] = status

    async def set_account_membership(self, uid, is_member):
        if self.membership_entered:
            self.membership_entered.set()
            await self.membership_release.wait()
        if uid in self.accounts:
            self.accounts[uid][1] = is_member

    async def bulk_upsert_accounts(self, accounts):
        for uid, _, _, _, status in accounts:
            self.accounts[uid] = [status, True]

    async def reconcile_members(self, ids):
        for uid in self.accounts:
            if uid not in ids:
                self.accounts[uid][1] = False

    async def sync_channels(self, channels):
        if self.sync_entered:
            self.sync_entered.set()
            await self.sync_release.wait()
        for cid in self.channels:
            self.channels[cid] = False
        for cid, _, active in channels:
            self.channels[cid] = active

    async def is_channel_exist(self, cid):
        return cid in self.channels

    async def create_channel(self, cid, name, active):
        self.channels[cid] = active

    async def bulk_save_periods(self, periods):
        if self.save_entered:
            self.save_entered.set()
            await self.save_release.wait()
        self.periods.extend(periods)


class Guild:
    def __init__(self):
        self.id = 10
        self.unavailable = False
        self.members = []
        self.chunk_members = []
        self.member_count = 0
        self.voice_channels = []
        self.afk_channel = None

    async def chunk(self, *, cache):
        return list(self.chunk_members)

    def get_member(self, uid):
        return next((member for member in self.members if member.id == uid), None)

    def get_channel(self, cid):
        return next((channel for channel in self.voice_channels if channel.id == cid), None)


def member(uid, guild, status=disnake.Status.online):
    return SimpleNamespace(id=uid, guild=guild, status=status, bot=False, voice=None,
                           display_avatar=None, name=f'user{uid}', display_name=f'user{uid}')


class MembershipTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.guild = Guild()
        self.repo = Repository()
        self.bot = SimpleNamespace(user=SimpleNamespace(id=999), get_guild=lambda _: self.guild)
        self.tracker = UserPresenceTracker.__new__(UserPresenceTracker)
        self.tracker.bot = self.bot
        self.tracker.guild_id = self.guild.id
        self.tracker.guild = self.guild
        self.tracker.repo = self.repo
        self.tracker.user_states = {}
        self.tracker._period_queue = deque()
        self.tracker._pending_status = {}
        self.tracker._pending_members = {}
        self.tracker._pending_membership = {}
        self.tracker._departed = set()
        self.tracker._membership_lock = asyncio.Lock()
        self.tracker._write_lock = asyncio.Lock()
        self.tracker._ready = True
        self.tracker._stopping = False

    async def test_leave_and_rejoin_preserve_period_and_start_new_one(self):
        user = member(1, self.guild)
        self.repo.accounts[1] = ['online', True]
        started = datetime.now(timezone.utc) - timedelta(minutes=2)
        self.tracker.user_states[1] = dict(state='online', channel_id=None, start_time=started)
        await self.tracker.on_member_remove(user)
        await self.tracker._drain_queue()
        self.assertEqual(self.repo.accounts[1], ['online', False])
        self.assertEqual(len(self.repo.periods), 1)
        self.assertEqual(self.repo.periods[0][2], started)
        self.assertNotIn(1, self.tracker.user_states)
        await self.tracker.on_member_join(user)
        await self.tracker._drain_queue()
        self.assertTrue(self.repo.accounts[1][1])
        self.assertGreater(self.tracker.user_states[1]['start_time'], started)

    async def test_new_user_join_leave_before_writer(self):
        user = member(2, self.guild)
        await self.tracker.on_member_join(user)
        # Windows' clock may return the same timestamp for back-to-back events.
        self.tracker.user_states[2]['start_time'] -= timedelta(seconds=1)
        await self.tracker.on_member_remove(user)
        await self.tracker._drain_queue()
        self.assertEqual(self.repo.accounts[2], ['online', False])
        self.assertNotIn(2, self.tracker.user_states)
        self.assertEqual(len(self.repo.periods), 1)

    async def test_return_during_pending_departure_write(self):
        user = member(1, self.guild)
        self.repo.accounts[1] = ['online', True]
        self.tracker.user_states[1] = dict(state='online', channel_id=None,
                                          start_time=datetime.now(timezone.utc) - timedelta(seconds=1))
        await self.tracker.on_member_remove(user)
        self.repo.membership_entered, self.repo.membership_release = asyncio.Event(), asyncio.Event()
        writing = asyncio.create_task(self.tracker._drain_queue())
        await self.repo.membership_entered.wait()
        await self.tracker.on_member_join(user)
        self.repo.membership_release.set()
        await writing
        self.repo.membership_entered = None
        await self.tracker._drain_queue()
        self.assertTrue(self.repo.accounts[1][1])
        self.assertIn(1, self.tracker.user_states)

    async def test_sync_uses_chunk_ids_and_preserves_cached_presence(self):
        current = member(1, self.guild)
        stale = member(2, self.guild)
        chunk_copy = member(1, self.guild, disnake.Status.offline)
        self.guild.members = [current, stale]
        self.guild.chunk_members = [chunk_copy]
        self.guild.member_count = 1
        self.guild.voice_channels = [SimpleNamespace(id=4, name='current')]
        self.repo.accounts = {1: ['online', True], 2: ['online', True]}
        self.repo.channels = {3: True}
        self.tracker.user_states[2] = dict(state='online', channel_id=None, start_time=datetime.now(timezone.utc))
        await self.tracker._sync_profiles()
        self.assertEqual(self.repo.accounts[1], ['online', True])
        self.assertFalse(self.repo.accounts[2][1])
        self.assertNotIn(2, self.tracker.user_states)
        self.assertEqual(self.repo.periods, [])
        self.assertEqual(self.repo.channels, {3: False, 4: True})

    async def test_incomplete_chunk_does_not_mark_users_left(self):
        current = member(1, self.guild)
        self.guild.members = self.guild.chunk_members = [current]
        self.guild.member_count = 2
        self.repo.accounts = {2: ['online', True]}
        await self.tracker._sync_profiles()
        self.assertTrue(self.repo.accounts[2][1])

    async def test_join_during_sync_is_applied_after_snapshot(self):
        user = member(1, self.guild)
        self.repo.sync_entered, self.repo.sync_release = asyncio.Event(), asyncio.Event()
        syncing = asyncio.create_task(self.tracker._sync_profiles())
        await self.repo.sync_entered.wait()
        joining = asyncio.create_task(self.tracker.on_member_join(user))
        await asyncio.sleep(0)
        self.repo.sync_release.set()
        await asyncio.gather(syncing, joining)
        await self.tracker._drain_queue()
        self.assertTrue(self.repo.accounts[1][1])
        self.assertIn(1, self.tracker.user_states)

    async def test_period_queued_during_write_is_not_lost(self):
        self.repo.accounts[1] = ['online', True]
        start = datetime.now(timezone.utc) - timedelta(minutes=2)
        end = start + timedelta(minutes=1)
        self.tracker.record_state_period(1, 'online', start, end)
        self.repo.save_entered, self.repo.save_release = asyncio.Event(), asyncio.Event()
        writing = asyncio.create_task(self.tracker._drain_queue())
        await self.repo.save_entered.wait()
        self.tracker.record_state_period(1, 'online', end, end + timedelta(minutes=1))
        self.repo.save_release.set()
        await writing
        await self.tracker._drain_queue()
        self.assertEqual(len(self.repo.periods), 2)


if __name__ == '__main__':
    unittest.main()
