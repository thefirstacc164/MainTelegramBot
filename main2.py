import logging
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


def get_gemini_model(context: ContextTypes.DEFAULT_TYPE):
    if not GENAI_AVAILABLE: return None
    api_key = context.bot_data.get("GEMINI_API_KEY")
    if not api_key: return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.0-flash')


# ═══════════════════════════════════════════
# AI SYSTEM & AUTO-DESTRUCT
# ═══════════════════════════════════════════

async def start_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if not GENAI_AVAILABLE or not context.bot_data.get("GEMINI_API_KEY"):
        await query.edit_message_text("❌ AI is not configured. Missing API Key or library.")
        return
    
    # Initialize session with msg_ids array for complete clean up later
    context.bot_data.setdefault("ai_sessions", {})[user_id] = {
        "active": True,
        "history": [],
        "msg_ids": []
    }
    
    text = (
        "🤖 <b>AI Mode Active (Gemini)</b>\n\n"
        "Send text or images to chat. I will remember context.\n\n"
        "⚠️ <b>IMPORTANT:</b> Type <code>/done</code> when you are finished.\n"
        "This will close the session and <b>permanently delete every message</b> "
        "from this chat to leave absolutely no trace."
    )
    
    msg = await query.edit_message_text(text, parse_mode=ParseMode.HTML)
    
    # Track the menu message ID so we can delete it later
    context.bot_data["ai_sessions"][user_id]["msg_ids"].append(msg.message_id)


async def execute_smart_done(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """
    The Smart /done command for AI.
    Wipes the Gemini memory AND deletes every single message from the Telegram chat.
    """
    session = context.bot_data.get("ai_sessions", {}).get(user_id)
    chat_id = update.effective_chat.id
    
    # Track the actual '/done' message the user just sent so we delete it too
    if update.message:
        session["msg_ids"].append(update.message.message_id)
        
    # Send a temporary status message
    status = await context.bot.send_message(chat_id, "🧹 Purging AI memory and scrubbing chat history...")
    
    # 1. Delete all tracked messages from Telegram
    for mid in session.get("msg_ids", []):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass # Ignore if already deleted
            
    # 2. Delete the status message
    try:
        await status.delete()
    except Exception:
        pass
        
    # 3. Erase bot memory
    del context.bot_data["ai_sessions"][user_id]
    
    # Return to the clean main menu
    from main1 import cmd_start
    await cmd_start(update, context)


async def handle_ai_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text in AI mode."""
    user_id = update.message.from_user.id
    session = context.bot_data["ai_sessions"][user_id]
    
    # Track User's prompt for deletion
    session["msg_ids"].append(update.message.message_id)
    
    user_text = update.message.text.strip()
    if not user_text: return
    
    await context.bot.send_chat_action(chat_id=update.message.chat_id, action="typing")
    model = get_gemini_model(context)
    history = session.get("history", [])
    history.append({"role": "user", "parts": [user_text]})
    
    try:
        chat = model.start_chat(history=[{"role": h["role"], "parts": h["parts"]} for h in history[:-1]])
        response = chat.send_message(user_text)
        
        history.append({"role": "model", "parts": [response.text]})
        if len(history) > 40: history = history[-40:]
        session["history"] = history
        
        # Try markdown, fallback to plain
        try:
            msg = await update.message.reply_text(response.text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            msg = await update.message.reply_text(response.text)
            
        # Track AI's response for deletion
        session["msg_ids"].append(msg.message_id)
        
    except Exception as e:
        err = await update.message.reply_text(f"❌ AI Error: {str(e)[:200]}")
        session["msg_ids"].append(err.message_id)
        if history: history.pop()


async def handle_ai_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle images in AI mode with full vision model parsing."""
    user_id = update.message.from_user.id
    session = context.bot_data["ai_sessions"][user_id]
    
    # Track User's image for deletion
    session["msg_ids"].append(update.message.message_id)
    
    await context.bot.send_chat_action(chat_id=update.message.chat_id, action="typing")
    
    try:
        if update.message.photo: photo = update.message.photo[-1]
        elif update.message.document: photo = update.message.document
        else: return
        
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        caption = update.message.caption or "Analyze and describe this image in detail."
        
        import PIL.Image
        image = PIL.Image.open(io.BytesIO(image_bytes))
        
        model = get_gemini_model(context)
        response = model.generate_content([caption, image])
        
        # Add to history
        history = session.get("history", [])
        history.append({"role": "user", "parts": [f"[Sent Image: {caption}]"]})
        history.append({"role": "model", "parts": [response.text]})
        session["history"] = history
        
        try:
            msg = await update.message.reply_text(response.text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            msg = await update.message.reply_text(response.text)
            
        # Track AI's response for deletion
        session["msg_ids"].append(msg.message_id)
        
    except Exception as e:
        err = await update.message.reply_text(f"❌ Error analyzing image: {str(e)[:200]}")
        session["msg_ids"].append(err.message_id)


# ═══════════════════════════════════════════
# MASTER ROUTERS (Replaces main1 handlers)
# ═══════════════════════════════════════════

async def master_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routes all text messages. Processes the smart /done command, Search mode, and AI mode."""
    if not update.message or not update.message.from_user: return
    user_id = update.message.from_user.id
    text = update.message.text.strip().lower()
    
    # 1. SMART /done LOGIC
    if text == "/done":
        # If in AI Mode -> Self Destruct
        if context.bot_data.get("ai_sessions", {}).get(user_id, {}).get("active"):
            await execute_smart_done(update, context, user_id)
            return
            
        # If in Upload Mode -> Finalize Upload
        if context.bot_data.get("upload_sessions", {}).get(user_id, {}).get("active"):
            from main1 import _process_upload
            try: await update.message.delete() # Clean UI
            except: pass
            await _process_upload(update, context, user_id, is_callback=False)
            return
            
        # If /done pressed out of context, just delete it
        try: await update.message.delete()
        except: pass
        return

    # 2. SEARCH MODE
    if context.bot_data.get("search_sessions", {}).get(user_id):
        from main1 import handle_search_input
        await handle_search_input(update, context)
        return

    # 3. AI MODE
    if context.bot_data.get("ai_sessions", {}).get(user_id, {}).get("active"):
        await handle_ai_text(update, context)
        return
        
    # 4. TRASH CLEANUP (If user types random text outside of modes, delete it to keep chat clean)
    try: await update.message.delete()
    except: pass


async def master_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routes files. Processes AI vision mode vs main1 Upload mode."""
    if not update.message or not update.message.from_user: return
    user_id = update.message.from_user.id
    
    # 1. AI MODE (Vision)
    if context.bot_data.get("ai_sessions", {}).get(user_id, {}).get("active"):
        if update.message.photo or (update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("image/")):
            await handle_ai_image(update, context)
            return
        else:
            # Not an image, but in AI mode. Track and delete it.
            context.bot_data["ai_sessions"][user_id]["msg_ids"].append(update.message.message_id)
            msg = await update.message.reply_text("❌ AI mode only accepts images and text.")
            context.bot_data["ai_sessions"][user_id]["msg_ids"].append(msg.message_id)
            return

    # 2. UPLOAD MODE
    if context.bot_data.get("upload_sessions", {}).get(user_id, {}).get("active"):
        from main1 import handle_file_upload
        await handle_file_upload(update, context)
        return
        
    # 3. TRASH CLEANUP (Random files sent outside of upload mode are deleted)
    try: await update.message.delete()
    except: pass


def register_handlers(app):
    # AI Menu Start
    app.add_handler(CallbackQueryHandler(start_ai_chat, pattern="^menu_ai$"))
    
    # Master Routers (Overriding generic text and file inputs)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, master_text_handler))
    
    app.add_handler(MessageHandler(
        (filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO | 
         filters.VOICE | filters.VIDEO_NOTE | filters.Sticker.ALL | 
         filters.ANIMATION) & filters.ChatType.PRIVATE,
        master_file_handler
    ))
    
    logger.info("Main2 handlers (Master Routers & AI Destruct) registered.")
