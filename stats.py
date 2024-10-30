import disnake
from disnake.ext import tasks
import json
import os
from datetime import datetime, timedelta, date
from plogging import Plogging
import asyncio

class StatisticsTracker:
    def __init__(self, bot, guild_id, stats_dir="stats", retention_days=7):
        self.bot = bot
        self.plogging = Plogging()
        self.guild_id = guild_id  # ID of the server to track
        self.stats_dir = stats_dir
        self.retention_days = retention_days  # Number of days to retain statistics
        self.user_states = {}  # Tracks the current state of users

        # Ensure the stats directory exists
        if not os.path.exists(self.stats_dir):
            os.makedirs(self.stats_dir)

        # Add an event listener for when the bot is ready
        self._start()
    def _start(self):
        asyncio.create_task(self.on_ready())

    async def on_ready(self):
        self.guild = self.bot.get_guild(self.guild_id)
        if not self.guild:
            await self.plogging.warn(f"Guild with ID {self.guild_id} not found.")
            return
        else:
            await self.plogging.debug(f"StatisticsTracker initialized for guild: {self.guild.name}")
            self.periodic_stats_update.start()
            self.clean_old_stats.start()
            self.compress_stats_files.start()

    def get_member_state(self, member):
        """Determine the current state of a member."""
        if member.status is disnake.Status.offline:
            return "offline"
        elif member.voice:
            if member.voice.self_deaf:
                return "voice_deaf"
            elif member.voice.self_mute:
                return "voice_mute"
            elif member.voice.channel == member.guild.afk_channel:
                return "voice_afk"
            elif len(member.voice.channel.members) == 1:
                return "voice_alone"
            else:
                return "voice_online"
        else:
            # Member is online but not in voice
            return "online"

    async def update_user_state(self, member):
        """Update the state of a member."""
        user_id = str(member.id)
        current_state = self.get_member_state(member)
        now = datetime.now().isoformat()
        previous_state_info = self.user_states.get(user_id)
        if previous_state_info:
            previous_state = previous_state_info["state"]
            start_time = previous_state_info["start_time"]
        else:
            # If no previous state, initialize
            previous_state = None
            start_time = now  # Assume the state started now
        if current_state != previous_state:
            # State has changed, record the previous state duration
            # Even if previous_state is None, we should record the initial state
            if previous_state is not None:
                # Record the period for the previous state
                self.record_state_period(user_id, member.name, previous_state, start_time, now)
            else:
                # Record the initial state starting from now
                self.record_state_period(user_id, member.name, current_state, start_time, now)
            # Update the state
            self.user_states[user_id] = {
                "state": current_state,
                "start_time": now
            }
        else:
            # State hasn't changed, do nothing
            pass

    def record_state_period(self, user_id, user_name, state, start_time, end_time):
        """Record the state period for a user."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        stats_path = os.path.join(self.stats_dir, f"{user_id}_{date_str}.json")
        # Create the data entry
        data_entry = {
            "state": state,
            "start_time": start_time,
            "end_time": end_time
        }

        try:
            # Load existing data
            if os.path.exists(stats_path):
                with open(stats_path, "r") as f:
                    data = json.load(f)
            else:
                data = {
                    "name": user_name,
                    "periods": []
                }
            # Append the new entry
            data["periods"].append(data_entry)

            # Save the data back
            with open(stats_path, "w") as f:
                json.dump(data, f)
        except Exception as e:
            asyncio.create_task(self.plogging.warn(f"Error recording state period for user {user_id}: {e}"))

    @tasks.loop(seconds=3)
    async def periodic_stats_update(self):
        """Periodic task to update user statistics."""
        # Get the guild
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            await self.plogging.error(f"Guild with ID {self.guild_id} not found.")
            return
        
        for member in guild.members:


            await self.update_user_state(member)

    @tasks.loop(hours=1)
    async def clean_old_stats(self):
        """Clean up old statistics files."""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            for file in os.listdir(self.stats_dir):
                # Files are named as {user_id}_{date}.json
                parts = file.split('_')
                if len(parts) >= 2 and file.endswith('.json'):
                    date_str = parts[-1].replace('.json', '')
                    try:
                        file_date = datetime.strptime(date_str, "%Y-%m-%d")
                        if file_date < cutoff_date:
                            os.remove(os.path.join(self.stats_dir, file))
                    except ValueError:
                        # Invalid date format in file name
                        continue
        except Exception as e:
            await self.plogging.error(f"Error cleaning old stats: {e}")

    @tasks.loop(minutes=1)
    async def compress_stats_files(self):
        """Compress stats files by merging similar consecutive entries."""
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            for file in os.listdir(self.stats_dir):
                # Skip today's files
                if today_str in file:
                    continue
                if file.endswith('.json'):
                    stats_path = os.path.join(self.stats_dir, file)
                    try:
                        with open(stats_path, "r") as f:
                            data = json.load(f)
                        periods = data.get("periods", [])
                        if periods:
                            compressed_periods = self.compress_periods(periods)
                            data["periods"] = compressed_periods
                            with open(stats_path, "w") as f:
                                json.dump(data, f)
                    except Exception as e:
                        await self.plogging.error(f"Error compressing file {file}: {e}")
        except Exception as e:
            await self.plogging.error(f"Error in compress_stats_files: {e}")

    def compress_periods(self, periods):
        """Compress periods by merging similar consecutive entries."""
        if not periods:
            return periods

        compressed = []
        prev_entry = periods[0]
        for entry in periods[1:]:
            if entry["state"] == prev_entry["state"]:
                # Extend the end_time of prev_entry
                prev_entry["end_time"] = entry["end_time"]
            else:
                compressed.append(prev_entry)
                prev_entry = entry
        compressed.append(prev_entry)
        return compressed

    def get_user_stats(self, user_id, day='previous'):
        """
        Get user stats for a given day or range of days.
        """
        user_name = None

        # Parse the day parameter
        if day == 'today':
            date_list = [datetime.now().date()]
        elif day == 'previous':
            date_list = [(datetime.now() - timedelta(days=1)).date()]
        elif isinstance(day, str):
            if '-' in day:
                # Range of dates in 'YYYY.MM.DD - YYYY.MM.DD' format
                start_str, end_str = day.split('-')
                start_date = datetime.strptime(start_str.strip(), '%Y.%m.%d').date()
                end_date = datetime.strptime(end_str.strip(), '%Y.%m.%d').date()
                if start_date > end_date:
                    start_date, end_date = end_date, start_date
                date_list = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
            else:
                # Single date in 'YYYY.MM.DD' format
                single_date = datetime.strptime(day.strip(), '%Y.%m.%d').date()
                date_list = [single_date]
        elif isinstance(day, date):
            date_list = [day]
        elif isinstance(day, (list, tuple)):
            date_list = day
        else:
            raise ValueError("Invalid day parameter")

        stats = {}

        for single_date in date_list:
            date_str = single_date.strftime('%Y-%m-%d')
            stats_path = os.path.join(self.stats_dir, f"{user_id}_{date_str}.json")
            if os.path.exists(stats_path):
                with open(stats_path, 'r') as f:
                    data = json.load(f)
                    if not user_name:
                        user_name = data.get('name', 'Unknown')
                    periods = data.get('periods', [])
            else:
                # No stats file for this date
                periods = []
                if not user_name:
                    user_name = 'Unknown'

            # Process periods and compute total times
            total_times = self.process_periods(single_date, periods)
            stats[date_str] = total_times

        return {'name': user_name, 'days': stats}

    def process_periods(self, single_date, periods):
        """
        Given a date and a list of periods, fill gaps with 'offline' and compute total time per state.
        Returns a dictionary of total times per state in hours with one decimal place.
        """
        day_start = datetime.combine(single_date, datetime.min.time())
        day_end = datetime.combine(single_date, datetime.max.time())

        # Convert periods to datetime objects and adjust times
        adjusted_periods = []
        for period in periods:
            try:
                start_time = datetime.fromisoformat(period['start_time'])
                end_time = datetime.fromisoformat(period['end_time'])
            except ValueError:
                continue

            # Adjust times to be within the day
            if end_time < day_start or start_time > day_end:
                continue
            if start_time < day_start:
                start_time = day_start
            if end_time > day_end:
                end_time = day_end

            adjusted_periods.append({
                'state': period['state'],
                'start_time': start_time,
                'end_time': end_time
            })

        # Sort periods by start_time
        adjusted_periods.sort(key=lambda x: x['start_time'])

        # Fill gaps with 'offline'
        filled_periods = []
        current_time = day_start

        for period in adjusted_periods:
            if period['start_time'] > current_time:
                filled_periods.append({
                    'state': 'offline',
                    'start_time': current_time,
                    'end_time': period['start_time']
                })
            filled_periods.append(period)
            current_time = period['end_time']

        if current_time < day_end:
            filled_periods.append({
                'state': 'offline',
                'start_time': current_time,
                'end_time': day_end
            })

        # Compute total times per state
        total_times = {}
        for period in filled_periods:
            state = period['state']
            duration = (period['end_time'] - period['start_time']).total_seconds()
            total_times[state] = total_times.get(state, 0) + duration

        # Format times in hours with one decimal place
        total_times_formatted = {}
        for state, duration in total_times.items():
            hours = duration / 3600
            total_times_formatted[state] = f"{hours:.2f}h"

        return total_times_formatted