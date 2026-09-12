import os
import logging
from telegram.ext import ApplicationBuilder

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Main loader - loads environment and registers all handlers."""
    
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set!")
        return

    # Build application
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Store config in bot_data for access everywhere
    app.bot_data["GEMINI_API_KEY"] = GEMINI_API_KEY
    app.bot_data["STORAGE_CHAT_ID"] = None  # Will be set via /setstorage
    app.bot_data["topics"] = {}  # topic_name -> topic_id mapping
    app.bot_data["file_index"] = []  # list of indexed files
    app.bot_data["upload_sessions"] = {}  # user_id -> session data
    app.bot_data["ai_sessions"] = {}  # user_id -> conversation history
    
    # Load handlers from main1 (storage + upload + search)
    from main1 import register_handlers as register_main1
    register_main1(app)
    
    # Load handlers from main2 (AI / Gemini)
    from main2 import register_handlers as register_main2
    register_main2(app)
    
    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
