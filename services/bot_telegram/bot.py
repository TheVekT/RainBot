from telegram import Update, BotCommand, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from telegram.error import Forbidden, BadRequest

# Conversation states
GET_THRESHOLD = 0

class TelegramBot:
    """
    Telegram Bot implementation for sending rain notifications and configuring user thresholds.
    """
    def __init__(self, token: str, db):
        self.application = Application.builder().token(token).build()
        self.db = db
        self.active_messages = {}  # Cache of sent messages: {user_id: message_id}
        self.register_handlers()

    def register_handlers(self):
        """
        Registers Telegram command and conversation handlers.
        """
        self.application.add_handler(CommandHandler('start', self.cmd_start))
        self.application.add_handler(CommandHandler('off', self.cmd_off))
        
        # Threshold setup conversation
        threshold_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('set', self.cmd_set)],
            states={
                GET_THRESHOLD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_threshold)]
            },
            fallbacks=[CommandHandler('cancel', self.cmd_cancel)]
        )
        self.application.add_handler(threshold_conv_handler)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handles the /start command. Saves the user with a threshold of -1 (notifications disabled).
        """
        user_id = update.effective_user.id
        await self.db.set_user_threshold(user_id, -1)
        
        await update.message.reply_text(
            "Hello! I am a rain notification bot.\n"
            "To receive notifications, set a scrap threshold using the /set command."
        )

    async def cmd_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handles the /off command. Sets threshold to -1 to disable notifications without deleting the user.
        """
        user_id = update.effective_user.id
        await self.db.set_user_threshold(user_id, -1)
        
        await update.message.reply_text("Notifications disabled. Use /set to enable them again.")

    async def cmd_set(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Initiates the threshold setup conversation.
        """
        user_id = update.effective_user.id
        current = await self.db.get_user_threshold(user_id)
        
        status_msg = "Notifications are currently disabled (-1)." if current == -1 else f"Your current threshold is: {current}."
        
        await update.message.reply_text(
            f"{status_msg}\n"
            "Enter a new value (minimum 20) or /cancel to abort:",
            reply_markup=ReplyKeyboardRemove()
        )
        return GET_THRESHOLD

    async def process_threshold(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Validates and processes the threshold value input by the user.
        """
        user_id = update.effective_user.id
        try:
            threshold = int(update.message.text)
            threshold = max(threshold, 20)  # Enforce minimum threshold of 20
            
            await self.db.set_user_threshold(user_id, threshold)
            await update.message.reply_text(f"Threshold successfully set to {threshold}.")
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("Please enter a valid number.")
            return GET_THRESHOLD

    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Cancels the threshold configuration conversation.
        """
        await update.message.reply_text("Configuration cancelled.")
        return ConversationHandler.END

    # --- Methods invoked externally (via gRPC) ---

    async def broadcast_rain_start(self, scrap_amount: float):
        """
        Broadcasts a notification to all users whose thresholds are met when a rain event starts.
        Ignores users with threshold == -1.
        """
        self.active_messages.clear()
        users = await self.db.get_all_users()
        
        for user in users:
            # Skip if notifications are disabled (-1) or scrap amount is below threshold
            if user["threshold"] != -1 and scrap_amount >= user["threshold"]:
                try:
                    msg = await self.application.bot.send_message(
                        chat_id=user["user_id"],
                        text=f"🌧️ Rakeback Rain NOW!!! 🌧️\n\n$ {scrap_amount:.2f}"
                    )
                    self.active_messages[user["user_id"]] = msg.message_id
                except Forbidden:
                    # Remove user from DB if they blocked the bot
                    await self.db.remove_user(user["user_id"])

    async def broadcast_rain_update(self, scrap_amount: float):
        """
        Edits the text of previously sent messages to reflect the updated scrap amount.
        """
        for user_id, msg_id in self.active_messages.items():
            try:
                await self.application.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=msg_id,
                    text=f"🌧️ Rakeback Rain NOW!!! 🌧️\n\n$ {scrap_amount:.2f}"
                )
            except BadRequest:
                pass  # Message was either deleted or has not changed

    async def broadcast_rain_end(self, scrap_amount: float):
        """
        Performs the final update to messages when the rain event ends.
        """
        await self.broadcast_rain_update(scrap_amount)
        self.active_messages.clear()

    async def set_commands(self):
        """
        Registers bot commands in the Telegram menu.
        """
        commands = [
            BotCommand("start", "Start interacting with the bot"),
            BotCommand("set", "Set the threshold for rain notifications"),
            BotCommand("off", "Disable rain notifications")
        ]
        await self.application.bot.set_my_commands(commands)