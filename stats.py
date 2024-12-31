import disnake
from disnake.ext import tasks
import os
import asyncio
import sqlite3
from datetime import datetime, timedelta, date
from plogging import Plogging


def get_member_state(member: disnake.Member) -> str:
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


class StatisticsTracker:
    def __init__(self, bot, guild_id, db_path="stats/stats.db", retention_days=7):
        self.bot = bot
        self.plogging = Plogging()
        self.guild_id = guild_id  # ID of the server to track
        self.retention_days = retention_days  # Number of days to retain statistics
        self.user_states = {}  # Tracks the current state of users

        # Ensure the stats directory exists
        stats_dir = os.path.dirname(db_path)
        if stats_dir and not os.path.exists(stats_dir):
            os.makedirs(stats_dir)

        # Initialize database
        self.db_path = db_path
        self.init_db()

        # Add an event listener for when the bot is ready
        self._start()

    def _start(self):
        asyncio.create_task(self.on_ready())

    def init_db(self):
        """Initialize the SQLite database and create the table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")  
        conn.execute("PRAGMA synchronous=FULL;")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS user_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            state TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL
        )
        """)
        conn.commit()
        conn.close()

    async def on_ready(self):
        self.guild = self.bot.get_guild(self.guild_id)
        if not self.guild:
            await self.plogging.warn(f"Guild with ID {self.guild_id} not found.")
            return
        else:
            await self.plogging.debug(f"StatisticsTracker initialized for guild: {self.guild.name}")
            self.periodic_stats_update.start()
            self.clean_old_stats.start()
            self.compress_stats.start()

    async def update_user_state(self, member):
        """Update the state of a member."""
        user_id = str(member.id)
        current_state = get_member_state(member)
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
            # State changed
            if previous_state is not None:
                # Record the previous period
                await self.record_state_period(user_id, member.name, previous_state, start_time, now)
            else:
                # Initial state record
                await self.record_state_period(user_id, member.name, current_state, start_time, now)
            # Update the state
            self.user_states[user_id] = {
                "state": current_state,
                "start_time": now
            }

    async def record_state_period(self, user_id, user_name, state, start_time, end_time):
        """Record the state period for a user in the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
            INSERT INTO user_states (user_id, user_name, state, start_time, end_time)
            VALUES (?, ?, ?, ?, ?)
            """, (user_id, user_name, state, start_time, end_time))
            conn.commit()
            conn.close()
        except Exception as e:
            await self.plogging.warn(f"Error recording state period for user {user_id}: {e}")

    def find_member(self, nickname: str) -> disnake.Member:
        """Find a discord member by nickname."""
        member = self.guild.get_member_named(nickname)
        return member

    @tasks.loop(seconds=3)
    async def periodic_stats_update(self):
        """Periodic task to update user statistics."""
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            await self.plogging.error(f"Guild with ID {self.guild_id} not found.")
            return

        for member in guild.members:
            await self.update_user_state(member)

    @tasks.loop(hours=1)
    async def clean_old_stats(self):
        """Clean up old statistics records from the database."""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        cutoff_iso = cutoff_date.isoformat()
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("DELETE FROM user_states WHERE end_time < ?", (cutoff_iso,))
            conn.commit()
            conn.close()
        except Exception as e:
            await self.plogging.error(f"Error cleaning old stats: {e}")

    @tasks.loop(minutes=10)
    async def compress_stats(self):
        """
        Compress records by merging consecutive entries with the same state for each user.
        This reduces fragmentation and data size.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            # Выбираем все записи, отсортированные по user_id, start_time
            rows = conn.execute("""
            SELECT id, user_id, user_name, state, start_time, end_time
            FROM user_states
            ORDER BY user_id, start_time
            """).fetchall()

            # Обходим и сливаем одинаковые состояния
            merged = []
            prev = None

            for row in rows:
                r = {
                    'id': row[0],
                    'user_id': row[1],
                    'user_name': row[2],
                    'state': row[3],
                    'start_time': datetime.fromisoformat(row[4]),
                    'end_time': datetime.fromisoformat(row[5])
                }
                if prev and prev['user_id'] == r['user_id'] and prev['state'] == r['state'] and prev['end_time'] == r['start_time']:
                    # Сливаем
                    prev['end_time'] = r['end_time']
                else:
                    if prev:
                        merged.append(prev)
                    prev = r
            if prev:
                merged.append(prev)

            # Перезаписываем таблицу (атомарно)
            # Можно использовать транзакцию
            conn.execute("DELETE FROM user_states")  # Очистим
            for m in merged:
                conn.execute("""
                INSERT INTO user_states (user_id, user_name, state, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
                """, (m['user_id'], m['user_name'], m['state'], m['start_time'].isoformat(), m['end_time'].isoformat()))

            conn.commit()
            conn.close()

        except Exception as e:
            await self.plogging.error(f"Error in compress_stats: {e}")

    def get_user_stats(self, user_id, day='previous'):
        """
        Get user stats for a given day or range of days from the database.
        Returns None if no data is found or if the date format is incorrect.
        """
        try:
            # Определяем даты
            if day == 'today':
                date_list = [datetime.now().date()]
            elif day == 'previous':
                date_list = [(datetime.now() - timedelta(days=1)).date()]
            elif isinstance(day, str):
                if '-' in day:
                    # Format: YYYY.MM.DD - YYYY.MM.DD
                    start_str, end_str = day.split('-')
                    start_date = datetime.strptime(start_str.strip(), '%Y.%m.%d').date()
                    end_date = datetime.strptime(end_str.strip(), '%Y.%m.%d').date()
                    if start_date > end_date:
                        start_date, end_date = end_date, start_date
                    date_list = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
                else:
                    # Single date
                    single_date = datetime.strptime(day.strip(), '%Y.%m.%d').date()
                    date_list = [single_date]
            elif isinstance(day, date):
                date_list = [day]
            elif isinstance(day, (list, tuple)):
                # Ensure all elements in the list/tuple are date objects
                date_list = []
                for d in day:
                    if isinstance(d, date):
                        date_list.append(d)
                    elif isinstance(d, str):
                        # Attempt to parse each string to a date
                        parsed_date = datetime.strptime(d.strip(), '%Y.%m.%d').date()
                        date_list.append(parsed_date)
                    else:
                        # If any element is neither a date nor a valid string, raise an error
                        raise ValueError("Invalid date in list/tuple")
            else:
                # If 'day' parameter is of an unexpected type
                return None  # Instead of raising ValueError
        except (ValueError, TypeError):
            # If date parsing fails or an invalid type is encountered
            return None

        user_name = None
        stats = {}

        try:
            # Подключаемся к БД для выборки
            conn = sqlite3.connect(self.db_path)

            for single_date in date_list:
                day_start = datetime.combine(single_date, datetime.min.time())
                day_end = datetime.combine(single_date, datetime.max.time())
                
                if single_date == datetime.now().date():
                    now = datetime.now()
                    if day_end > now:
                        day_end = now
                # Выборка периодов за конкретный день
                rows = conn.execute("""
                SELECT user_name, state, start_time, end_time
                FROM user_states
                WHERE user_id = ?
                AND ((start_time <= ? AND end_time >= ?) 
                    OR (start_time >= ? AND start_time <= ?))
                """, (
                    str(user_id),
                    day_end.isoformat(),
                    day_start.isoformat(),
                    day_start.isoformat(),
                    day_end.isoformat()
                )).fetchall()

                if not rows:
                    continue  # No data for this date, proceed to next

                periods = []
                for r in rows:
                    if not user_name:
                        user_name = r[0]
                    try:
                        s_time = datetime.fromisoformat(r[2])
                        e_time = datetime.fromisoformat(r[3])
                    except ValueError:
                        continue  # Skip rows with invalid datetime formats

                    # Обрезаем периоды по границам дня
                    if s_time < day_start:
                        s_time = day_start
                    if e_time > day_end:
                        e_time = day_end

                    if e_time > s_time:
                        periods.append({
                            'state': r[1],
                            'start_time': s_time,
                            'end_time': e_time
                        })

                # Process periods only if there are valid periods
                if periods:
                    total_times = self.process_periods(single_date, periods)
                    stats[single_date.strftime('%Y-%m-%d')] = total_times

        except sqlite3.Error:
            # Handle any database connection or query errors
            return None
        finally:
            conn.close()

        if not stats:
            # No data found for any of the dates
            return None

        if not user_name:
            user_name = "Unknown"

        return {'name': user_name, 'days': stats}

    def process_periods(self, single_date, periods):
        """
        Заполняет пропуски состоянием 'offline' и суммирует время.
        """
        day_start = datetime.combine(single_date, datetime.min.time())
        day_end = datetime.combine(single_date, datetime.max.time())

        # Сортируем периоды
        periods.sort(key=lambda x: x['start_time'])

        # Заполняем пропуски "offline"
        filled_periods = []
        current_time = day_start
        for period in periods:
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

        # Считаем суммарное время по состояниям
        total_times = {}
        for p in filled_periods:
            state = p['state']
            duration = (p['end_time'] - p['start_time']).total_seconds()
            total_times[state] = total_times.get(state, 0) + duration

        # Переводим в часы
        total_times_formatted = {s: f"{(d/3600):.2f}h" for s, d in total_times.items()}
        return total_times_formatted

    def stop(self):
        """Properly stop the StatisticsTracker, saving any pending data and stopping tasks."""
        now = datetime.now().isoformat()

        # Записываем текущие состояния пользователей в бд
        for user_id, state_info in self.user_states.items():
            current_state = state_info['state']
            start_time = state_info['start_time']

            # Получаем имя пользователя
            member = self.guild.get_member(int(user_id))
            user_name = member.name if member else 'Unknown'

            # Записываем период до текущего момента
            asyncio.run(self.record_state_period(user_id, user_name, current_state, start_time, now))

        # Останавливаем таски
        self.periodic_stats_update.cancel()
        self.clean_old_stats.cancel()
        self.compress_stats.cancel()

        # Очищаем состояние
        self.user_states.clear()