import disnake
from disnake.ext import tasks, commands
import os
import asyncio
import sqlite3
from datetime import datetime, timedelta, date
from rainbot.utils import Plogging

def get_member_state(member: disnake.Member) -> str:
    """Determine the current state of a member."""
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

class StatisticsTracker:
    """
    StatisticsTracker is a class that monitors and records the states of users in a Discord server.
    It logs transitions such as online, offline, and various voice channel statuses (like muted or deafened),
    along with corresponding timestamps. This data is stored in a partitioned SQLite database, and the class
    periodically updates user states for further analysis and reporting.
    """
    def __init__(self, bot, guild_id, db_path="stats/stats.db", retention_days=7, plogging: Plogging | None = None):
        self.bot: commands.Bot = bot
        self.plogging = Plogging() if plogging is None else plogging
        self.guild_id = guild_id
        self.retention_days = retention_days
        self.user_states = {}  # {user_id: {"state": str, "start_time": ISO string}}

        stats_dir = os.path.dirname(db_path)
        if stats_dir and not os.path.exists(stats_dir):
            os.makedirs(stats_dir)
        self.db_path = db_path
        self.init_db_master()
        self._start()

    def _start(self):
        asyncio.create_task(self.on_ready())
        # Запускаем задачу периодической фиксации текущего состояния (каждые 10 минут)
        self.periodic_state_fixation.start()

    def init_db_master(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=FULL;")
        conn.commit()
        conn.close()

    def _get_partition_table(self, dt: datetime) -> str:
        return "user_states_" + dt.strftime("%Y_%m_%d")

    def _ensure_partition_table(self, conn, table_name: str):
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                state TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL
            )
        """)
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_user_id ON {table_name}(user_id)")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_start_time ON {table_name}(start_time)")

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
        user_id = str(member.id)
        current_state = get_member_state(member)
        now = datetime.now().isoformat()
        previous_state_info = self.user_states.get(user_id)
        if previous_state_info:
            previous_state = previous_state_info["state"]
            start_time = previous_state_info["start_time"]
        else:
            previous_state = None
            start_time = now
        if current_state != previous_state:
            # Если состояние изменилось, записываем период для старого состояния
            await self.record_state_period(user_id, member.name, previous_state if previous_state is not None else current_state, start_time, now)
            self.user_states[user_id] = {"state": current_state, "start_time": now}

    async def record_state_period(self, user_id, user_name, state, start_time, end_time):
        """Записывает период состояния, разбивая его по границам дней, если необходимо."""
        try:
            dt_start = datetime.fromisoformat(start_time)
            dt_end = datetime.fromisoformat(end_time)
        except Exception as e:
            await self.plogging.warn(f"Invalid datetime format for user {user_id}: {e}")
            return

        # Если период пересекает границу дня, разбиваем его
        if dt_start.date() != dt_end.date():
            await self.record_period_split(user_id, user_name, state, dt_start, dt_end)
        else:
            table_name = self._get_partition_table(dt_start)
            conn = sqlite3.connect(self.db_path)
            self._ensure_partition_table(conn, table_name)
            conn.execute(f"""
                INSERT INTO {table_name} (user_id, user_name, state, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, user_name, state, start_time, end_time))
            conn.commit()
            conn.close()

    async def record_period_split(self, user_id, user_name, state, dt_start, dt_end):
        """Разбивает период, пересекающий границу дня, на несколько записей."""
        conn = sqlite3.connect(self.db_path)
        while dt_start.date() < dt_end.date():
            table_name = self._get_partition_table(dt_start)
            self._ensure_partition_table(conn, table_name)
            # Конец дня: 23:59:59
            end_of_day = datetime.combine(dt_start.date(), datetime.max.time())
            # Если разница меньше секунды, пропускаем
            if end_of_day < dt_start:
                break
            conn.execute(f"""
                INSERT INTO {table_name} (user_id, user_name, state, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, user_name, state, dt_start.isoformat(), end_of_day.isoformat()))
            await self.plogging.debug(f"Splitting period for user {user_id}: {dt_start.isoformat()} -> {end_of_day.isoformat()}")
            dt_start = datetime.combine(dt_start.date() + timedelta(days=1), datetime.min.time())
        # Последняя часть
        table_name = self._get_partition_table(dt_start)
        self._ensure_partition_table(conn, table_name)
        conn.execute(f"""
            INSERT INTO {table_name} (user_id, user_name, state, start_time, end_time)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, user_name, state, dt_start.isoformat(), dt_end.isoformat()))
        await self.plogging.debug(f"Final split period for user {user_id}: {dt_start.isoformat()} -> {dt_end.isoformat()}")
        conn.commit()
        conn.close()

    def find_member(self, nickname: str) -> disnake.Member:
        return self.guild.get_member_named(nickname)

    @tasks.loop(seconds=3)
    async def periodic_stats_update(self):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            await self.plogging.error(f"Guild with ID {self.guild_id} not found.")
            return
        tasks_list = [self.update_user_state(member) for member in guild.members]
        await asyncio.gather(*tasks_list, return_exceptions=True)

    @tasks.loop(minutes=10)
    async def periodic_state_fixation(self):
        """
        Периодически фиксирует текущее состояние пользователей, даже если оно не изменилось.
        Это помогает «сбросить» период, чтобы гарантировать запись активного состояния.
        """
        now = datetime.now().isoformat()
        await self.plogging.debug("Fixing stats periods")
        for user_id, state_info in self.user_states.items():
            # Фиксируем период, если прошло более 10 минут с последней записи
            last_time = datetime.fromisoformat(state_info["start_time"])
            if (datetime.now() - last_time) >= timedelta(minutes=10):
                member = self.guild.get_member(int(user_id))
                user_name = member.name if member else "Unknown"
                await self.record_state_period(user_id, user_name, state_info["state"], state_info["start_time"], now)
                # Обновляем стартовую точку до текущего времени
                self.user_states[user_id]["start_time"] = now
                await self.plogging.debug(f"Periodic fixation for user {user_id}: fixed up to {now}")

    @tasks.loop(hours=1)
    async def clean_old_stats(self):
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        cutoff_iso = cutoff_date.isoformat()
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'user_states_%'")
            tables = [row[0] for row in cur.fetchall()]
            for table in tables:
                conn.execute(f"DELETE FROM {table} WHERE end_time < ?", (cutoff_iso,))
            conn.commit()
            conn.close()
        except Exception as e:
            await self.plogging.error(f"Error cleaning old stats: {e}")

    @tasks.loop(minutes=10)
    async def compress_stats(self):
        """
        Сжимает записи внутри каждой партиции, объединяя подряд идущие периоды одного пользователя,
        если разница между ними не превышает 1 секунды. Вся операция обёрнута в транзакцию.
        Добавлено подробное логирование.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'user_states_%'")
            tables = [row[0] for row in cur.fetchall()]
            for table in tables:
                await self.plogging.debug(f"Compressing table {table}")
                rows = conn.execute(f"""
                    SELECT id, user_id, user_name, state, start_time, end_time
                    FROM {table}
                    ORDER BY user_id, start_time
                """).fetchall()
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
                    if prev and prev['user_id'] == r['user_id'] and prev['state'] == r['state']:
                        gap = (r['start_time'] - prev['end_time']).total_seconds()
                        if gap <= 1:
                            prev['end_time'] = r['end_time']
                            await self.plogging.debug(f"Merged with previous: new end_time = {prev['end_time'].isoformat()}")
                            continue
                    if prev:
                        merged.append(prev)
                    prev = r
                if prev:
                    merged.append(prev)
                # Оборачиваем операцию в транзакцию
                conn.execute("BEGIN TRANSACTION")
                conn.execute(f"DELETE FROM {table}")
                for m in merged:
                    conn.execute(f"""
                        INSERT INTO {table} (user_id, user_name, state, start_time, end_time)
                        VALUES (?, ?, ?, ?, ?)
                    """, (m['user_id'], m['user_name'], m['state'],
                          m['start_time'].isoformat(), m['end_time'].isoformat()))
                conn.commit()
                await self.plogging.debug(f"Table {table} compressed: {len(merged)} records saved.")
            conn.close()
        except Exception as e:
            await self.plogging.error(f"Error in compress_stats: {e}")

    def get_user_timeline(self, user_id, day='previous'):
        try:
            if day == 'today':
                date_list = [datetime.now().date()]
            elif day == 'previous':
                date_list = [(datetime.now() - timedelta(days=1)).date()]
            elif isinstance(day, str):
                single_date = datetime.strptime(day.strip(), '%Y.%m.%d').date()
                date_list = [single_date]
            elif isinstance(day, date):
                date_list = [day]
            else:
                return None
        except (ValueError, TypeError):
            return None

        target_date = date_list[0]
        day_start = datetime.combine(target_date, datetime.min.time())
        day_end = datetime.combine(target_date, datetime.max.time())
        if target_date == datetime.now().date():
            now = datetime.now()
            if day_end > now:
                day_end = now

        timeline = []
        user_name = None
        conn = sqlite3.connect(self.db_path)
        try:
            table_name = self._get_partition_table(day_start)
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            if not cur.fetchone():
                conn.close()
                return None

            rows = conn.execute(f"""
                SELECT user_name, state, start_time, end_time
                FROM {table_name}
                WHERE user_id = ?
                AND ((start_time <= ? AND end_time >= ?)
                    OR (start_time >= ? AND start_time <= ?))
                ORDER BY start_time
            """, (
                str(user_id),
                day_end.isoformat(),
                day_start.isoformat(),
                day_start.isoformat(),
                day_end.isoformat()
            )).fetchall()

            if not rows:
                conn.close()
                return None

            periods = []
            for r in rows:
                if not user_name:
                    user_name = r[0]
                try:
                    s_time = datetime.fromisoformat(r[2])
                    e_time = datetime.fromisoformat(r[3])
                except ValueError:
                    continue
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
            if not periods:
                conn.close()
                return None

            timeline = []
            current_time = day_start
            for period in periods:
                if period['start_time'] > current_time:
                    timeline.append({
                        'state': 'offline',
                        'start_time': current_time.isoformat(),
                        'end_time': period['start_time'].isoformat()
                    })
                if timeline and timeline[-1]['state'] == period['state']:
                    prev_end = datetime.fromisoformat(timeline[-1]['end_time'])
                    gap = (period['start_time'] - prev_end).total_seconds()
                    if gap <= 1:
                        timeline[-1]['end_time'] = period['end_time'].isoformat()
                    else:
                        timeline.append({
                            'state': period['state'],
                            'start_time': period['start_time'].isoformat(),
                            'end_time': period['end_time'].isoformat()
                        })
                else:
                    timeline.append({
                        'state': period['state'],
                        'start_time': period['start_time'].isoformat(),
                        'end_time': period['end_time'].isoformat()
                    })
                current_time = period['end_time']
            if current_time < day_end:
                timeline.append({
                    'state': 'offline',
                    'start_time': current_time.isoformat(),
                    'end_time': day_end.isoformat()
                })
            conn.close()
            return {'name': user_name if user_name else "Unknown", 'timeline': timeline}
        except sqlite3.Error:
            conn.close()
            return None

    def get_user_stats(self, user_id, day='previous'):
        try:
            if day == 'today':
                date_list = [datetime.now().date()]
            elif day == 'previous':
                date_list = [(datetime.now() - timedelta(days=1)).date()]
            elif isinstance(day, str):
                if '-' in day:
                    start_str, end_str = day.split('-')
                    start_date = datetime.strptime(start_str.strip(), '%Y.%m.%d').date()
                    end_date = datetime.strptime(end_str.strip(), '%Y.%m.%d').date()
                    if start_date > end_date:
                        start_date, end_date = end_date, start_date
                    date_list = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
                else:
                    single_date = datetime.strptime(day.strip(), '%Y.%m.%d').date()
                    date_list = [single_date]
            elif isinstance(day, date):
                date_list = [day]
            elif isinstance(day, (list, tuple)):
                date_list = []
                for d in day:
                    if isinstance(d, date):
                        date_list.append(d)
                    elif isinstance(d, str):
                        parsed_date = datetime.strptime(d.strip(), '%Y.%m.%d').date()
                        date_list.append(parsed_date)
                    else:
                        raise ValueError("Invalid date in list/tuple")
            else:
                return None
        except (ValueError, TypeError):
            return None

        user_name = None
        stats = {}
        conn = sqlite3.connect(self.db_path)
        try:
            for single_date in date_list:
                day_start = datetime.combine(single_date, datetime.min.time())
                day_end = datetime.combine(single_date, datetime.max.time())
                if single_date == datetime.now().date():
                    now = datetime.now()
                    if day_end > now:
                        day_end = now
                table_name = self._get_partition_table(day_start)
                cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if not cur.fetchone():
                    continue
                rows = conn.execute(f"""
                    SELECT user_name, state, start_time, end_time
                    FROM {table_name}
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
                    continue
                periods = []
                for r in rows:
                    if not user_name:
                        user_name = r[0]
                    try:
                        s_time = datetime.fromisoformat(r[2])
                        e_time = datetime.fromisoformat(r[3])
                    except ValueError:
                        continue
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
                if periods:
                    total_times = self.process_periods(single_date, periods)
                    stats[single_date.strftime('%Y-%m-%d')] = total_times
        except sqlite3.Error:
            return None
        finally:
            conn.close()

        if not stats:
            return None
        if not user_name:
            user_name = "Unknown"
        return {'name': user_name, 'days': stats}

    def process_periods(self, single_date, periods):
        day_start = datetime.combine(single_date, datetime.min.time())
        day_end = datetime.combine(single_date, datetime.max.time())
        periods.sort(key=lambda x: x['start_time'])
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
        total_times = {}
        for p in filled_periods:
            state = p['state']
            duration = (p['end_time'] - p['start_time']).total_seconds()
            total_times[state] = total_times.get(state, 0) + duration
        total_times_formatted = {s: f"{(d/3600):.2f}h" for s, d in total_times.items()}
        return total_times_formatted

    def stop(self):
        now = datetime.now().isoformat()
        for user_id, state_info in self.user_states.items():
            current_state = state_info['state']
            start_time = state_info['start_time']
            member = self.guild.get_member(int(user_id))
            user_name = member.name if member else 'Unknown'
            asyncio.run(self.record_state_period(user_id, user_name, current_state, start_time, now))
        self.periodic_stats_update.cancel()
        self.clean_old_stats.cancel()
        self.compress_stats.cancel()
        self.periodic_state_fixation.cancel()
        self.user_states.clear()

    def get_all_users(self) -> dict:
        guild = self.guild if hasattr(self, 'guild') and self.guild else self.bot.get_guild(self.guild_id)
        if guild is None:
            return {}
        users_data = {}
        for member in guild.members:
            avatar_url = member.display_avatar.url if member.display_avatar else None
            users_data[str(member.id)] = {
                'nickname': member.name,
                'avatar_url': avatar_url,
                'status': get_member_state(member)
            }
        return users_data




class RainStats:
    def __init__(self, rainparser, plogging: Plogging | None = None, db_path: str = "stats/rain_stats.db", retention_days: int = 90):
        
        self.rainparser = rainparser
        self.plogging = Plogging() if plogging is None else plogging
        self.rainparser.rain_end.connect(lambda scrap_amount, user_count: asyncio.create_task(self.on_rain_end(scrap_amount, user_count)))
        self.db_path = db_path
        self.init_db()
        self.clean_old_stats.start()
        self.retention_days = retention_days

    def init_db(self):
        """Инициализирует базу данных и создает необходимые таблицы."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=FULL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rain_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scrap_amount REAL NOT NULL,
                user_count INTEGER NOT NULL,
                time TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rain_stats_time ON rain_stats(time)")
        conn.commit()
        conn.close()

    async def on_rain_end(self, scrap_amount: float, user_count: int):
        """Обработчик сигнала окончания рейна."""
        try:
            now = datetime.now().isoformat()
            
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT INTO rain_stats (scrap_amount, user_count, time)
                VALUES (?, ?, ?)
            """, (scrap_amount, user_count, now))
            conn.commit()
            conn.close()
            
            await self.plogging.debug(f"Recorded rain stats: {scrap_amount} scrap, {user_count} users")
        except Exception as e:
            await self.plogging.error(f"Error recording rain stats: {e}")

    @tasks.loop(hours=24)
    async def clean_old_stats(self):
        """Очищает статистику старше X дней."""
        try:
            cutoff_date = (datetime.now() - timedelta(days=self.retention_days)).isoformat()
            conn = sqlite3.connect(self.db_path)
            conn.execute("DELETE FROM rain_stats WHERE time < ?", (cutoff_date,))
            conn.commit()
            conn.close()
            await self.plogging.debug("Cleaned old rain stats")
        except Exception as e:
            await self.plogging.error(f"Error cleaning old rain stats: {e}")

    def stop(self):
        """Останавливает все задачи."""
        self.clean_old_stats.cancel()

    
    
