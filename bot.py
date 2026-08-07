"""
Main Pyrogram Bot Client & Lifecycle Manager
Initializes the Telegram Bot Client, manages MongoDB database connections,
sets up the web server for Render health checks, and registers command/event plugins.
"""

import asyncio
import logging
from aiohttp import web
from pyrogram import Client, __version__ as pyrogram_version

from config import Config
from database import db
from utils.logger import setup_logger

# Initialize structured logging
logger = setup_logger("BotEngine")


class MovieBot(Client):
    def __init__(self) -> None:
        super().__init__(
            name="MovieManagementBot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins=dict(root="plugins"),
            workers=min(32, (Config.PORT or 8080) + 4),
        )
        self.web_runner: web.AppRunner | None = None

    async def start(self) -> None:
        """Starts the bot engine, connects to MongoDB, and binds health server."""
        logger.info("Initializing Movie Management Bot...")
        
        # 1. Connect to MongoDB Atlas
        await db.connect()
        
        # 2. Start Pyrogram Client
        await super().start()
        bot_info = await self.get_me()
        logger.info(f"Bot started as @{bot_info.username} (ID: {bot_info.id})")
        logger.info(f"Running on Pyrogram v{pyrogram_version}")

        # 3. Start Health Check HTTP Server (Render.com Keep-Alive)
        await self._start_health_server()

        # 4. Send Startup Notification to Admin Log Channel
        if Config.LOG_CHANNEL_ID:
            try:
                await self.send_message(
                    chat_id=Config.LOG_CHANNEL_ID,
                    text=(
                        "🚀 **Movie Bot Started Successfully!**\n\n"
                        f"• **Bot Name:** {bot_info.first_name}\n"
                        f"• **Username:** @{bot_info.username}\n"
                        f"• **Pyrogram:** v{pyrogram_version}\n"
                        f"• **Render Port:** {Config.PORT}"
                    ),
                )
            except Exception as e:
                logger.warning(f"Could not send startup log message: {e}")

    async def stop(self, *args) -> None:
        """Gracefully shuts down bot, database connection, and web server."""
        logger.info("Initiating graceful shutdown...")

        # 1. Stop Health Check Web Server
        if self.web_runner:
            await self.web_runner.cleanup()
            logger.info("Health check server stopped.")

        # 2. Stop Pyrogram Client
        await super().stop()

        # 3. Close MongoDB Atlas Connection
        await db.close()

        logger.info("Bot stopped cleanly.")

    async def _start_health_server(self) -> None:
        """Starts lightweight aiohttp server for Render health checks."""
        app = web.Application()
        app.router.add_get("/", self._health_check_handler)
        app.router.add_get("/health", self._health_check_handler)

        self.web_runner = web.AppRunner(app)
        await self.web_runner.setup()
        site = web.TCPSite(self.web_runner, Config.HOST, Config.PORT)
        await site.start()
        logger.info(f"Health check endpoint listening on http://{Config.HOST}:{Config.PORT}/health")

    async def _health_check_handler(self, request: web.Request) -> web.Response:
        """Responds to Render keep-alive pings."""
        return web.json_response(
            {
                "status": "online",
                "database": "connected" if db.db is not None else "disconnected",
                "service": "Telegram Movie Management Bot",
            },
            status=200,
        )


if __name__ == "__main__":
    bot = MovieBot()
    bot.run()
