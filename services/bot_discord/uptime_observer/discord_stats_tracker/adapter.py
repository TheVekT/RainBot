"""Read tracker lifecycle signals without adding monitoring to the tracker."""


class DiscordStatsAdapter:
    def __init__(self, tracker, bot):
        self.tracker = tracker
        self.bot = bot

    def snapshot(self):
        tracker = self.tracker
        loops = ('write_queue', 'periodic_state_fixation', 'daily_profile_sync',
                 'clean_old_stats', 'compress_stats')
        stopped = [name for name in loops if not getattr(tracker, name).is_running()]
        guild = tracker.guild
        return {
            'tracker': 'stopping' if tracker._stopping else ('ready' if tracker._ready else 'starting'),
            'gateway': 'ready' if self.bot.is_ready() and not self.bot.is_closed() else 'not_ready',
            'guild': 'unavailable' if guild is None or guild.unavailable else 'available',
            'background_tasks': 'stopped' if stopped else 'running',
            'stopped_tasks': stopped,
        }
