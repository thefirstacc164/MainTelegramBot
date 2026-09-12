import os
import logging
from telegram.ext import ApplicationBuilder

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    GITHUB_REPO = os.environ.get("GITHUB_REPO", "thefirstacc164/MainTelegramBot")
    
    if not all([BOT_TOKEN, GEMINI_API_KEY, GITHUB_TOKEN]):
        logger.error("Missing Environment Variables! Need BOT_TOKEN, GEMINI_API_KEY, and GITHUB_TOKEN.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Store global config
    app.bot_data["GEMINI_API_KEY"] = GEMINI_API_KEY
    app.bot_data["GITHUB_TOKEN"] = GITHUB_TOKEN
    app.bot_data["GITHUB_REPO"] = GITHUB_REPO
    
    # Initialize state
    app.bot_data["STORAGE_CHAT_ID"] = None 
    app.bot_data["topics"] = {} 
    app.bot_data["file_index"] = [] 
    
    app.bot_data["upload_sessions"] = {}
    app.bot_data["search_sessions"] = {}
    app.bot_data["ai_sessions"] = {} 
    
    # Load handlers
    from main1 import register_handlers as register_main1
    register_main1(app)
    
    from main2 import register_handlers as register_main2
    register_main2(app)
    
    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
