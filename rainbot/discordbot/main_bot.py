import disnake
import datetime
import asyncio
from rainbot.websocket import WebSocketServer
from disnake.ext import commands, tasks
from rainbot.utils import StatisticsTracker, ConfigManager, Plogging, RainStats
from rainbot.telegrambot import TelegramBot
from rainbot.discordbot import RainParser, PlaySoundOnBot
from rainbot import DISCORD_TOKEN, TELEGRAM_TOKEN

bot_already_was_ready = False

plogging = Plogging()
plogging.set_websocket_settings(debug=False, error=False)
plogging.set_folders(info='main_logs', error='debug_logs', warn='main_logs', debug='debug_logs')
plogging.enable_logging()

intents = disnake.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True
intents.guilds = True
intents.presences = True


activity = disnake.Activity(
    name="геноцид.",
    type=disnake.ActivityType.competing,
)
bot = commands.Bot(command_prefix="/", intents=intents, activity=activity)


@tasks.loop(seconds=10)
async def searching_rain():
    await rain.check_event()

@tasks.loop(seconds=300)    
async def restarting_browser():
    await rain.restart_browser()



@bot.event
async def on_ready():
    global bot_already_was_ready
    if bot_already_was_ready:
        await plogging.info('Bot is already running, skipping RE-initialization.')
        return
    global cdown, sound, rain, stats, teleg_bot, rain_stats, server
    cdown = ConfigManager(plogging=plogging)
    await cdown.create_config()
    stats = StatisticsTracker(bot=bot, guild_id=901174571225448479, retention_days=700, plogging=plogging)
    sound = PlaySoundOnBot(bot, plogging=plogging)
    rain = RainParser(plogging=plogging)
    rain_stats = RainStats(rain, plogging=plogging, retention_days=365)
    if rain.bot is None:
        rain.connect_bot(bot)
    server = WebSocketServer(host='192.168.0.106', plogging=plogging, stats=stats)

    teleg_bot = TelegramBot(TELEGRAM_TOKEN, rain, plogging=plogging)
    teleg_bot.connect_discord_module(stats)
    await teleg_bot.start_polling()

    server.register_funcs({
            'stop': stop,
            'plogging': plogging.info,
            'restart': restart,
            'shlepay': shlepay,
            'nalivai': nalivai,
            'stop_full': shutdown_stop 
        })
    server.run()
    if not searching_rain.is_running():
        searching_rain.start()
    if not restarting_browser.is_running():
        restarting_browser.start()


    await plogging.info('Bot is ready!')
    bot_already_was_ready = True




    
#░█████╗░░█████╗░███╗░░░███╗███╗░░░███╗░█████╗░███╗░░██╗██████╗░░██████╗
#██╔══██╗██╔══██╗████╗░████║████╗░████║██╔══██╗████╗░██║██╔══██╗██╔════╝
#██║░░╚═╝██║░░██║██╔████╔██║██╔████╔██║███████║██╔██╗██║██║░░██║╚█████╗░
#██║░░██╗██║░░██║██║╚██╔╝██║██║╚██╔╝██║██╔══██║██║╚████║██║░░██║░╚═══██╗
#╚█████╔╝╚█████╔╝██║░╚═╝░██║██║░╚═╝░██║██║░░██║██║░╚███║██████╔╝██████╔╝
#░╚════╝░░╚════╝░╚═╝░░░░░╚═╝╚═╝░░░░░╚═╝╚═╝░░╚═╝╚═╝░░╚══╝╚═════╝░╚═════╝░

last_use_time = {}

# Определяем ID разрешённых голосовых каналов
ALLOWED_VOICE_CHANNEL_IDS = [1168637408896622672, 901174980673425408, 1168637791278739497]

# Функция для автодополнения
async def autocomplete_voice_channels(interaction: disnake.ApplicationCommandInteraction, user_input: str):
    # Получаем все голосовые каналы на сервере
    guild = interaction.guild
    allowed_channels = [
        channel for channel in guild.voice_channels
        if channel.id in ALLOWED_VOICE_CHANNEL_IDS
    ]

    # Фильтруем каналы по имени с учётом пользовательского ввода
    choices = [
        disnake.OptionChoice(name=channel.name, value=str(channel.id))
        for channel in allowed_channels
        if user_input.lower() in channel.name.lower()
    ]

    return choices[:25]  # Ограничиваем 25 вариантами

@bot.slash_command(name="shlepki", description="Play sound shlepki.", guild_ids=[901174571225448479])
async def shlepki(ctx):
    await plogging.info(f"Command 'shlepki' was used by {ctx.author.display_name}")

    await ctx.response.defer(ephemeral=True)
    
    channel_id = ctx.author.voice.channel.id if ctx.author.voice else None
    if not channel_id:
        await plogging.info(f"Declined. User {ctx.author.display_name} is not in a voice channel.")
        await ctx.followup.send("You need to be in a voice channel to use this command.")
        return
    user_id = ctx.author.id
    if not hasattr(shlepki, 'last_use_time'):
        shlepki.last_use_time = {}  # Создаем словарь для хранения времени последнего использования команды
    
    user_id = ctx.author.id
    if user_id in shlepki.last_use_time:
        last_use_time = shlepki.last_use_time[user_id]
        cooldown = await cdown.check_user_cooldown(member_id=user_id, command_name="shlepki", last_command_use=last_use_time)
        if cooldown != 0:
            await ctx.followup.send(f"You have {cooldown} sec. cooldown left for this command.")
            await plogging.info(f"Declined. User have a {cooldown} sec. cooldown.")
            return   
        
  # Устанавливаем текущее время как время последнего использования команды для данного пользователя
    shlepki.last_use_time[user_id] = datetime.datetime.now()

    # Запускаем воспроизведение звука асинхронно
    asyncio.create_task(sound.bot_sound(sound.play_audio, *("shlepki.mp3", 72, 0.6), channel_id=channel_id))
    embed = disnake.Embed(
        description="Playing sound.",
        colour=0xF0C43F,
    )
    embed.set_footer(
        text="© RainBot",
    )
    await ctx.followup.send(embed=embed)  
  


@bot.slash_command(name="moving", description="Move a user tuda syuda.", guild_ids=[901174571225448479])
async def moving(ctx: disnake.ApplicationCommandInteraction, member: disnake.Member):
    try:
        await ctx.response.defer(ephemeral=True)
        await plogging.info(f"Command   'moving'   was used by   {ctx.author.display_name}\nTry to moving {member.display_name}")
        # Проверяем, присоединен ли участник к голосовому каналу
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await plogging.info(f"Declined. User {ctx.author.display_name} is not in a voice channel.")
            embed = disnake.Embed(
                description=f"You are not in a voice channel!",
                colour=0xF0C43F,
            )
            embed.set_footer(
                text="© RainBot",
            ) 
            await ctx.followup.send(embed=embed)
            return
        if member.voice is None or member.voice.channel is None:
            await plogging.info(f"Declined. Target {member.display_name} is not in a voice channel.")
            embed = disnake.Embed(
                description=f"{member.mention} is not connected to a voice channel.",
                colour=0xF0C43F,
            )
            embed.set_footer(
                text="© RainBot",
            ) 
            await ctx.followup.send(embed=embed)
            return
    #koja protection
        if member.id in (1084386974967812167, -1) or member.voice.self_stream or member.voice.self_video:
            await plogging.info("Target has immunity.")
            embed = disnake.Embed(
                description=f"This user has immunity.",
                colour=0xF0C43F,
            )
            embed.set_footer(
                text="© RainBot",
            ) 
            await ctx.followup.send(embed=embed)
        
            return
        
        user_id = ctx.author.id
        if not hasattr(moving, 'last_use_time'):
            moving.last_use_time = {}  # Создаем словарь для хранения времени последнего использования команды
           
        
        user_id = ctx.author.id
        if user_id in moving.last_use_time:
            last_use_time = moving.last_use_time[user_id]
            cooldown = await cdown.check_user_cooldown(member_id=user_id, command_name="moving", last_command_use=last_use_time)
            if cooldown != 0:
                embed = disnake.Embed(
                    description=f"You have {cooldown} sec. cooldown left for this command.",
                    colour=0xF0C43F,
                )
                embed.set_footer(
                    text="© RainBot",
                ) 
                await ctx.followup.send(embed=embed)
                await plogging.info(f"Declined. User have a {cooldown} sec. cooldown.")
                return

        # Устанавливаем текущее время как время последнего использования команды для данного пользователя
        moving.last_use_time[user_id] = datetime.datetime.now()

        # Получаем текущий канал участника
        current_channel = member.voice.channel
        channel1 = ctx.guild.get_channel(1212058316138872902)
        channel2 = ctx.guild.get_channel(1212058374796218459)
        for i in range(1, 2, 1):
            # Перемещаем участника в указанный канал
            await member.move_to(channel1)
            # Перемещаем участника обратно в исходный канал
            await member.move_to(channel2)
        await member.move_to(current_channel)
        embed = disnake.Embed(
            description="Successfully.",
            colour=0xF0C43F,
        )
        embed.set_footer(
            text="© RainBot",
        ) 
        await ctx.followup.send(embed=embed)
    except disnake.errors.Forbidden:
        await ctx.followup.send("I don't have permissions to move users.")
    except disnake.errors.HTTPException:
        await ctx.followup.send("Failed to move the user.")
        
@bot.slash_command(name="move", description="Move a user to a specified voice channel.", guild_ids=[901174571225448479])
async def move(ctx: disnake.ApplicationCommandInteraction, member: disnake.Member, channel: str = commands.Param(autocomplete=autocomplete_voice_channels)):
    
    try:
        channel = ctx.guild.get_channel(int(channel))
        await ctx.response.defer(ephemeral=True)
        
        await plogging.info(f"Command 'move' was used by {ctx.author.display_name}\nTry to move {member.display_name} to {channel.name}")
        # Проверяем, подключен ли участник к каналу
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            embed = disnake.Embed(
                description="You are not in a voice channel!",
                colour=0xF0C43F,
            )
            embed.set_footer(
                text="© RainBot",
            )
            await plogging.warn(f"Declined. User {ctx.author.display_name} is not in a voice channel.")
            await ctx.followup.send(embed=embed)
            return
        if member.voice is None or member.voice.channel is None:
            await plogging.warn(f"Declined. Target {member.display_name} is not in a voice channel.")
            embed = disnake.Embed(
                description=f"{member.mention} is not connected to a voice channel.",
                colour=0xF0C43F,
            )
            embed.set_footer(
                text="© RainBot",
            )
            await ctx.followup.send(embed=embed)
            return
    #koja protection
        if member.id in (1084386974967812167, -1) or member.voice.self_stream or member.voice.self_video:
            await plogging.info("Target has immunity.")
            embed = disnake.Embed(
                description=f"This user has immunity.",
                colour=0xF0C43F,
            )
            embed.set_footer(
                text="© RainBot",
            ) 
            await ctx.followup.send(embed=embed)
        
            return
        
        

        user_id = ctx.author.id
        if not hasattr(move, 'last_use_time'):
            move.last_use_time = {}  # Создаем словарь для хранения времени последнего использования команды
        
        user_id = ctx.author.id
        if user_id in move.last_use_time:
            last_use_time = move.last_use_time[user_id]
            cooldown = await cdown.check_user_cooldown(member_id=user_id, command_name="move", last_command_use=last_use_time)
            if cooldown != 0:
                embed = disnake.Embed(
                description=f"You have {cooldown} sec. cooldown left for this command.",
                colour=0xF0C43F,
                )
                embed.set_footer(
                    text="© RainBot",
                )
                await ctx.followup.send(embed=embed)
                await plogging.info(f"User have a {cooldown} sec. cooldown.")
                return

        # Устанавливаем текущее время как время последнего использования команды для данного пользователя
        move.last_use_time[user_id] = datetime.datetime.now()
        
        await member.move_to(channel)
        embed = disnake.Embed(
            description=f"{member.mention} successfully moved to {channel.mention}.",
            colour=0xF0C43F,
        )
        embed.set_footer(
            text="© RainBot",
        )
        await ctx.followup.send(embed=embed)        
    except disnake.errors.Forbidden:
        await ctx.followup.send("I don't have permissions to move users.")
    except disnake.errors.HTTPException:
        await ctx.followup.send("Failed to move the user.")
    except Exception as e:
        await ctx.followup.send(f"An error occurred: {e}", ephemeral=True)



@bot.slash_command(name="getstats", description="Get user statistics.", guild_ids=[901174571225448479])
async def getstats(ctx: disnake.ApplicationCommandInteraction, member: disnake.Member = None, date: str = None):
    await ctx.response.defer(ephemeral=True)
    
    if date is None and member is None:
        embed = disnake.Embed(
        description="Incorect date.",
        colour=0xF0C43F,
        )
        embed.add_field(
            name="Usage",
            value="`/getstats @user date`\nSingle date format: YYYY.MM.DD, example: 2024.12.29\nDate range format: YYYY.MM.DD - YYYY.MM.DD, example: 2024.12.29 - 2024.12.31",
            inline=False)
        embed.set_footer(
            text="© RainBot",
        )
        await ctx.followup.send(embed=embed)
        
        return
    await plogging.info(f"Command 'getstats' was used by {ctx.author.display_name}")

    date = 'previous' if date is None else date
    
    if not hasattr(getstats, 'last_use_time'):
        getstats.last_use_time = {}  # Создаем словарь для хранения времени последнего использования команды
    
    user_id = ctx.author.id
    if user_id in getstats.last_use_time:
        last_use_time = getstats.last_use_time[user_id]
        cooldown = await cdown.check_user_cooldown(member_id=user_id, command_name="getstats", last_command_use=last_use_time)
        if cooldown != 0:
            embed = disnake.Embed(
            description=f"You have {cooldown} sec. cooldown left for this command.",
            colour=0xF0C43F,
            )
            embed.set_footer(
                text="© RainBot",
            )
            await ctx.followup.send(embed=embed)
            await plogging.info(f"User have a {cooldown} sec. cooldown.")
            return
        
    stats_data = stats.get_user_stats(member.id, date)
    await plogging.debug(f'Stats data: {stats_data}')
    if stats_data:
        embed = disnake.Embed(
            title=f"Statistics for {member.name}",
            description="Here is the requested user statistics:",
            colour=0xF0C43F,
        )
        embed.set_thumbnail(url=member.avatar.url)  # Иконка мембера
        for day, day_stat in stats_data['days'].items():
            text = f'''
            **Voice Time:** {day_stat.get("voice_online", 0)},
            **Mute:** {day_stat.get("voice_mute", 0)},
            **Full mute:** {day_stat.get("voice_deaf", 0)},
            **Online time:** {day_stat.get("online", 0)},
            **Offline time:** {day_stat.get("offline", 0)},
            **Voice alone:** {day_stat.get("voice_alone", 0)},
            '''
            embed.add_field(name=f" **{day}** ", value=text, inline=False)
        embed.set_footer(text="© RainBot")
        
        await ctx.followup.send(embed=embed, ephemeral=False)
    else:
        await ctx.followup.send("No statistics found for this user in this date range.")
    
    
    getstats.last_use_time[user_id] = datetime.datetime.now()    
    
    
    
    
    
@bot.slash_command(name="test", description="test command.")
async def test(ctx: disnake.ApplicationCommandInteraction):

    await plogging.info(f"Command 'test' was used by {ctx.author.display_name}")

    await ctx.response.defer(ephemeral=True)
    user_id = ctx.author.id
    if not hasattr(test, 'last_use_time'):
        test.last_use_time = {}  # Создаем словарь для хранения времени последнего использования команды
    
    user_id = ctx.author.id
    if user_id in test.last_use_time:
        last_use_time = test.last_use_time[user_id]
        cooldown = await cdown.check_user_cooldown(member_id=user_id, command_name="test", last_command_use=last_use_time)
        if cooldown != 0:
            await ctx.followup.send(f"You have {cooldown} sec. cooldown left for this command.")
            await plogging.info(f"User have a {cooldown} sec. cooldown.")
            return   
        
  # Устанавливаем текущее время как время последнего использования команды для данного пользователя
    test.last_use_time[user_id] = datetime.datetime.now()
    embed = disnake.Embed(
        description="Test successfully.",
        colour=0xF0C43F,
    )
    embed.set_footer(
    text="© RainBot",
    )
    await ctx.followup.send(embed=embed)  
    



mine_channel_ids = { 
    1: 1168637408896622672,
    2: 901174980673425408,
    3: 1168637791278739497
    }

async def shlepay(channel = None):

    await plogging.info(f"Command 'shlepki' from gui client")
    

    if channel in mine_channel_ids.keys():
        channel = mine_channel_ids[channel]
    else: 
        channel = None
    asyncio.create_task(sound.bot_sound(sound.play_audio, *("shlepki.mp3", 72, 0.6), channel_id=channel))

async def nalivai(channel = None):

    await plogging.info(f"Command 'nalivai' from gui client")

    if channel in mine_channel_ids.keys():
        channel = mine_channel_ids[channel]
    else: 
        channel = None
    await sound.bot_sound(sound.play_audio, *("sound.wav", 3.5, 0.6), channel_id=channel)




async def shutdown_stop(shutdown_delay_seconds: int = 180):
    import os
    minutes = shutdown_delay_seconds / 60
    await plogging.info(f'Stopping main script with shutdown in {minutes:.1f} minutes...')
    os.system(f"shutdown /s /t {shutdown_delay_seconds}")
    if searching_rain.is_running():
        searching_rain.stop()
    if restarting_browser.is_running():
        restarting_browser.stop()
    await rain.driver_quit()
    await rain.close_browsers()
    await bot.close()
    await teleg_bot.stop()
    plogging.archive_logs()
    stats.stop()


async def stop():
    await plogging.info('Stopping main script...')
    if searching_rain.is_running():
        searching_rain.stop()
    if restarting_browser.is_running():
        restarting_browser.stop()
    await rain.driver_quit()
    await rain.close_browsers()
    await server.shutdown()
    await bot.close()
    await teleg_bot.stop()
    plogging.archive_logs()
    stats.stop()
    
async def restart():
    await plogging.info('RESTARTING main script...')
    await rain.driver_quit()
    await rain.close_browsers()
    if restarting_browser.is_running():
        restarting_browser.stop()
        await asyncio.sleep(1)
        restarting_browser.start()
    if searching_rain.is_running():
        searching_rain.stop()
        await asyncio.sleep(1)
        rain.last_check_time = None
        searching_rain.start()


    











@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel != after.channel:
        if after.channel is None:
            await plogging.info(f"{member.display_name} left the voice channel {before.channel.name}.")
        elif before.channel is None:   
            await plogging.info(f"{member.display_name} joined to {after.channel.name}.")
        else:   
            await plogging.info(f"{member.display_name} moved from {before.channel.name} to {after.channel.name}.")    

    
    
    
    
    

     

async def try_connect():
    while True:
        try:
            # Запускаем бота, используя свой цикл событий
            await bot.start(DISCORD_TOKEN)
        except (disnake.HTTPException, disnake.GatewayNotFound, disnake.ConnectionClosed, OSError) as e:
            await plogging.warn(f"An error occurred: {e}")
            await plogging.info("Retrying in 30 seconds...")
            await asyncio.sleep(30)  # Ожидаем 30 секунд перед повторной попыткой
        else:
            # Если подключение прошло успешно, выходим из цикла
            break




