from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, error
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
import sqlite3
import asyncio
from plogging import Plogging
from stats import get_member_state

# Define states for the conversation
SET_THRESHOLD, GET_THRESHOLD, GET_DISCORD_NICK = range(3)

class TelegramBot:
    def __init__(self, token, rainparser, plogging: Plogging | None = None):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.rain = rainparser
        self.conn = sqlite3.connect('telegram-users.db')
        self.cursor = self.conn.cursor()
        self.create_table()
        self.register_handlers()
        self.init_connectors()
        self.active_events = {}  # Stores active user messages
        self.set_commands()
        self.plogging = Plogging() if plogging is None else plogging
        
    def connect_discord_module(self, module):
        self.discord = module
    
    def init_connectors(self):
        self.rain.rain_start.connect(self.on_rain_start)
        self.rain.rain_end.connect(self.on_rain_end)
        self.rain.rain_scrap.connect(self._on_rain_scrap)

    def create_table(self):
        """Creates the users table if it doesn't exist."""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                threshold INTEGER,
                discord_account TEXT
            )
        ''')
        self.conn.commit()
    
    def register_handlers(self):
        """Registers the bot's command handlers."""
        self.application.add_handler(CommandHandler('start', self.start))
        # Remove or comment out the following line
        # self.application.add_handler(CommandHandler('set', self.set_threshold))
        
        # Conversation handler for setting threshold
        threshold_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('set', self.set_threshold)],
            states={
                GET_THRESHOLD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_threshold)]
            },
            fallbacks=[CommandHandler('cancel', self.cancel)]
        )
        self.application.add_handler(threshold_conv_handler)

        # Add handlers for discord connection
        self.application.add_handler(CommandHandler('discord', self.discord_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, self.get_discord_nick))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for the /start command."""
        welcome_message = (
            "Hello! I am a bot for rain event notifications."
        )
        usage_message = (
            "To receive notifications, set a threshold value using the /set command.\n"
        )
        await update.message.reply_text(welcome_message)
        await update.message.reply_text(usage_message)

    async def set_threshold(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for the /set command to prompt the user for a threshold value."""
        user_id = update.effective_user.id

        # Получаем текущий порог для пользователя из базы данных
        self.cursor.execute('SELECT threshold FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()

        # Если порог не установлен (первоначальная настройка), используем значение по умолчанию
        current_threshold = result[0] if result else 20  # Default value is 20 if no threshold exists

        # Отправляем сообщение с текущим порогом
        await update.message.reply_text(
            f'Your current threshold is {current_threshold}. Please enter a new threshold value:',
            reply_markup=ReplyKeyboardRemove()
        )
        return GET_THRESHOLD

    async def get_threshold(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for getting the threshold value from the user."""
        user_id = update.effective_user.id
        try:
            # Преобразуем введенное значение в число
            threshold = int(update.message.text)

            # Убедимся, что порог не меньше 20
            if threshold < 20:
                threshold = 20

            discord_account = None  # Дискорд аккаунт не подключен по умолчанию

            # Сохраняем данные в базе данных
            self.cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, threshold, discord_account)
                VALUES (?, ?, ?)
            ''', (user_id, threshold, discord_account))
            self.conn.commit()

            # Отправляем сообщение об успешной установке порога
            await update.message.reply_text(f'Threshold set to {threshold}.')

            # Завершаем текущую сессию
            return ConversationHandler.END

        except ValueError:
            # Если введенное значение нельзя преобразовать в число
            await update.message.reply_text('Please enter a valid number.')
            return GET_THRESHOLD  # Оставляем пользователя в текущем состоянии для исправления ошибки

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler to cancel the conversation."""
        await update.message.reply_text('Operation cancelled.', reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    async def discord_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for the /discord command."""
        user_id = update.effective_user.id
        self.cursor.execute('SELECT discord_account FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        discord_account = result[0] if result else "not connected"

        keyboard = [
            [InlineKeyboardButton("Enter new nick", callback_data='connect')],
            [InlineKeyboardButton("Disconnect", callback_data='disconnect')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = f"Your current Discord account: {discord_account}"
        await update.message.reply_text(message, reply_markup=reply_markup)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for inline button callbacks."""
        query = update.callback_query
        user_id = query.from_user.id

        if query.data == 'connect':
            await query.message.edit_text("Please enter your new Discord nickname:")
            context.user_data['awaiting_nick'] = True
        elif query.data == 'disconnect':
            self.cursor.execute('UPDATE users SET discord_account = NULL WHERE user_id = ?', (user_id,))
            self.conn.commit()
            await query.message.edit_text("Your Discord account has been disconnected.")
    
    async def get_discord_nick(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for getting the Discord nick from the user."""
        user_id = update.effective_user.id
        if 'awaiting_nick' in context.user_data and context.user_data['awaiting_nick']:
            discord_nick = update.message.text
            self.cursor.execute('UPDATE users SET discord_account = ? WHERE user_id = ?', (discord_nick, user_id))
            self.conn.commit()
            await update.message.reply_text(f'Your Discord account has been set to {discord_nick}.')
            context.user_data['awaiting_nick'] = False

    def on_rain_start(self):
        """Starts the rain event."""
        self.active_events.clear()

    def on_rain_end(self):
        """Ends the rain event. Closes all active user events."""
        self.active_events.clear()

    def _on_rain_scrap(self, num):
        asyncio.create_task(self.on_rain_scrap(num))
        
    async def on_rain_scrap(self, num):
        """Handles the event of receiving a number during the rain."""
        self.cursor.execute("SELECT user_id, threshold, discord_account FROM users")
        users = self.cursor.fetchall()

        for user_id, threshold, discord_account in users:
            if num >= threshold:

                # Check if discord_account is not None or empty
                if discord_account:
                    # Try to find the Discord user
                    member = await self.discord.find_user(discord_account)
                    if member is not None:
                        state = get_member_state(member)
                        # If state is in specified states, skip this user
                        if state in ('voice_mute', 'voice_online'):
                            continue  # Skip sending message to this user


                # Proceed to send/update the Telegram message
                if user_id not in self.active_events:
                    # Send the first message to the user
                    message = await self.application.bot.send_message(
                        chat_id=user_id,
                        text=f"🌧️ Rakeback Rain NOW!!! 🌧️\n\n$ {num:.2f}"
                    )
                    self.active_events[user_id] = message
                else:
                    # Update the message
                    message = self.active_events[user_id]
                    try:
                        await message.edit_text(f"🌧️ Rakeback Rain NOW!!! 🌧️\n\n$ {num:.2f}")
                    except error.BadRequest:
                        pass
                    
    async def start_polling(self):
        """Asynchronously starts the bot in polling mode."""
        await self.application.initialize()  # Initialize the application
        await self.application.start()  # Start the bot in the existing event loop
        await self.application.updater.start_polling()  # Start polling
        await self.plogging.info("Telegram bot successfully started")  # Logging for debugging

    async def stop(self):
        """Stops the bot and closes the database connection."""
        await self.application.stop()
        self.conn.close()
            
    def set_commands(self):
        """Sets the bot's commands with descriptions."""
        commands = [
            BotCommand("start", "Start interacting with the bot."),
            BotCommand("set", "Set the threshold for rain notifications."),
            BotCommand("discord", "Edit your discord integration settings.")
        ]
        asyncio.create_task(self.application.bot.set_my_commands(commands))