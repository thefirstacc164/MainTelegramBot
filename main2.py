import logging
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CallbackQueryHandler, MessageHandler,
    CommandHandler, filters
)
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# Try to import Google Generative AI
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning("google-generativeai not installed. AI features disabled.")


def get_gemini_model(context: ContextTypes.DEFAULT_TYPE):
    """Initialize and return the Gemini model."""
    if not GENAI_AVAILABLE:
        return None
    
    api_key = context.bot_data.get("GEMINI_API_KEY")
    if not api_key:
        return None
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash')
    return model


# ═══════════════════════════════════════════
# AI CHAT SYSTEM
# ═══════════════════════════════════════════

async def start_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start an AI chat session."""
    query = update.callback_query
    is_callback = query is not None
    
    if is_callback:
        await query.answer()
        user_id = query.from_user.id
    else:
        user_id = update.message.from_user.id
    
    if not GENAI_AVAILABLE:
        msg = "❌ Google Generative AI library not installed."
        if is_callback:
            await query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return
    
    api_key = context.bot_data.get("GEMINI_API_KEY")
    if not api_key:
        msg = "❌ GEMINI_API_KEY not configured."
        if is_callback:
            await query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return
    
    # Initialize AI session
    context.bot_data.setdefault("ai_sessions", {})[user_id] = {
        "active": True,
        "history": []
    }
    
    keyboard = [
        [InlineKeyboardButton("🗑️ Clear History", callback_data="ai_clear")],
        [InlineKeyboardButton("🚪 Exit AI Chat", callback_data="ai_exit")],
    ]
    
    text = (
        "🤖 <b>AI Chat (Gemini)</b>\n\n"
        "I'm ready to chat! You can:\n"
        "• Send text messages\n"
        "• Send images (I'll analyze them)\n"
        "• Ask me anything!\n\n"
        "Type your message or send an image to get started.\n\n"
        "<i>To exit AI chat, press 🚪 Exit or type /exitai</i>"
    )
    
    if is_callback:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def cmd_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ai command."""
    await start_ai_chat(update, context)


async def cmd_exitai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /exitai command."""
    user_id = update.message.from_user.id
    if user_id in context.bot_data.get("ai_sessions", {}):
        del context.bot_data["ai_sessions"][user_id]
    
    from main1 import get_main_menu_keyboard
    await update.message.reply_text(
        "🚪 AI Chat ended. Back to main menu.",
        reply_markup=get_main_menu_keyboard()
    )


async def ai_exit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exit AI chat via button."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id in context.bot_data.get("ai_sessions", {}):
        del context.bot_data["ai_sessions"][user_id]
    
    from main1 import get_main_menu_keyboard
    await query.edit_message_text(
        "🚪 AI Chat ended. Back to main menu.",
        reply_markup=get_main_menu_keyboard()
    )


async def ai_clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear AI conversation history."""
    query = update.callback_query
    await query.answer("🗑️ History cleared!")
    
    user_id = query.from_user.id
    session = context.bot_data.get("ai_sessions", {}).get(user_id)
    if session:
        session["history"] = []
    
    keyboard = [
        [InlineKeyboardButton("🗑️ Clear History", callback_data="ai_clear")],
        [InlineKeyboardButton("🚪 Exit AI Chat", callback_data="ai_exit")],
    ]
    
    await query.edit_message_text(
        "🤖 <b>AI Chat (Gemini)</b>\n\n"
        "🗑️ Conversation history cleared!\n\n"
        "Send a new message to start fresh.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_ai_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages in AI chat mode."""
    user_id = update.message.from_user.id
    session = context.bot_data.get("ai_sessions", {}).get(user_id)
    
    if not session or not session.get("active"):
        return False  # Not in AI mode
    
    user_text = update.message.text.strip()
    if not user_text:
        return True
    
    # Show typing indicator
    await context.bot.send_chat_action(chat_id=update.message.chat_id, action="typing")
    
    model = get_gemini_model(context)
    if not model:
        await update.message.reply_text("❌ Failed to initialize AI model.")
        return True
    
    # Build conversation history for context
    history = session.get("history", [])
    
    # Add user message to history
    history.append({"role": "user", "parts": [user_text]})
    
    try:
        # Create chat with history
        chat = model.start_chat(history=[
            {"role": h["role"], "parts": h["parts"]}
            for h in history[:-1]  # All except current
        ])
        
        response = chat.send_message(user_text)
        ai_response = response.text
        
        # Add AI response to history
        history.append({"role": "model", "parts": [ai_response]})
        
        # Keep history manageable (last 20 exchanges)
        if len(history) > 40:
            history = history[-40:]
        
        session["history"] = history
        
        # Format and send response
        # Telegram has a 4096 character limit
        if len(ai_response) > 4000:
            # Split into chunks
            chunks = [ai_response[i:i+4000] for i in range(0, len(ai_response), 4000)]
            for i, chunk in enumerate(chunks):
                if i == len(chunks) - 1:
                    keyboard = [
                        [InlineKeyboardButton("🗑️ Clear", callback_data="ai_clear"),
                         InlineKeyboardButton("🚪 Exit", callback_data="ai_exit")],
                    ]
                    await update.message.reply_text(
                        chunk,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    await update.message.reply_text(chunk)
        else:
            keyboard = [
                [InlineKeyboardButton("🗑️ Clear", callback_data="ai_clear"),
                 InlineKeyboardButton("🚪 Exit", callback_data="ai_exit")],
            ]
            
            # Try to send with markdown, fallback to plain
            try:
                await update.message.reply_text(
                    ai_response,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception:
                await update.message.reply_text(
                    ai_response,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
    
    except Exception as e:
        logger.error(f"AI error: {e}")
        error_msg = str(e)[:200]
        
        keyboard = [
            [InlineKeyboardButton("🔄 Retry", callback_data="ai_retry")],
            [InlineKeyboardButton("🗑️ Clear", callback_data="ai_clear"),
             InlineKeyboardButton("🚪 Exit", callback_data="ai_exit")],
        ]
        
        await update.message.reply_text(
            f"❌ <b>AI Error:</b>\n<code>{error_msg}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Remove failed message from history
        if history and history[-1]["role"] == "user":
            history.pop()
    
    return True


async def handle_ai_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle image messages in AI chat mode."""
    user_id = update.message.from_user.id
    session = context.bot_data.get("ai_sessions", {}).get(user_id)
    
    if not session or not session.get("active"):
        return False  # Not in AI mode
    
    # Show typing indicator
    await context.bot.send_chat_action(chat_id=update.message.chat_id, action="typing")
    
    model = get_gemini_model(context)
    if not model:
        await update.message.reply_text("❌ Failed to initialize AI model.")
        return True
    
    try:
        # Get the photo (highest resolution)
        if update.message.photo:
            photo = update.message.photo[-1]
        elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("image/"):
            photo = update.message.document
        else:
            return True
        
        # Download the image
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        
        # Get caption/text if any
        caption = update.message.caption or "What's in this image? Describe it in detail."
        
        # Create image part for Gemini
        import PIL.Image
        image = PIL.Image.open(io.BytesIO(image_bytes))
        
        # Use vision model
        vision_model = genai.GenerativeModel('gemini-2.0-flash')
        response = vision_model.generate_content([caption, image])
        ai_response = response.text
        
        # Add to history (text only, can't easily store images)
        history = session.get("history", [])
        history.append({"role": "user", "parts": [f"[Sent an image with caption: {caption}]"]})
        history.append({"role": "model", "parts": [ai_response]})
        session["history"] = history
        
        keyboard = [
            [InlineKeyboardButton("🗑️ Clear", callback_data="ai_clear"),
             InlineKeyboardButton("🚪 Exit", callback_data="ai_exit")],
        ]
        
        if len(ai_response) > 4000:
            chunks = [ai_response[i:i+4000] for i in range(0, len(ai_response), 4000)]
            for i, chunk in enumerate(chunks):
                if i == len(chunks) - 1:
                    await update.message.reply_text(chunk, reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    await update.message.reply_text(chunk)
        else:
            try:
                await update.message.reply_text(
                    ai_response,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception:
                await update.message.reply_text(
                    ai_response,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
    
    except Exception as e:
        logger.error(f"AI image error: {e}")
        await update.message.reply_text(
            f"❌ Error analyzing image: {str(e)[:200]}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚪 Exit", callback_data="ai_exit")]
            ])
        )
    
    return True


async def ai_retry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retry the last AI message."""
    query = update.callback_query
    await query.answer("🔄 Retrying...")
    
    user_id = query.from_user.id
    session = context.bot_data.get("ai_sessions", {}).get(user_id)
    
    if not session or not session["history"]:
        await query.edit_message_text("❌ No message to retry.")
        return
    
    # Get last user message
    last_user_msg = None
    for msg in reversed(session["history"]):
        if msg["role"] == "user":
            last_user_msg = msg["parts"][0] if msg["parts"] else None
            break
    
    if not last_user_msg:
        await query.edit_message_text("❌ No message to retry.")
        return
    
    model = get_gemini_model(context)
    if not model:
        await query.edit_message_text("❌ Failed to initialize AI model.")
        return
    
    try:
        response = model.generate_content(last_user_msg)
        ai_response = response.text
        
        # Update history
        session["history"].append({"role": "model", "parts": [ai_response]})
        
        keyboard = [
            [InlineKeyboardButton("🗑️ Clear", callback_data="ai_clear"),
             InlineKeyboardButton("🚪 Exit", callback_data="ai_exit")],
        ]
        
        await query.edit_message_text(
            f"🔄 <b>Retried Response:</b>\n\n{ai_response[:3900]}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Retry failed: {str(e)[:200]}")


# ═══════════════════════════════════════════
# UNIFIED MESSAGE HANDLER
# This is the master router that checks AI mode first
# ═══════════════════════════════════════════

async def master_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master text handler - routes to AI or search/upload handlers."""
    if not update.message or not update.message.from_user:
        return
    
    user_id = update.message.from_user.id
    
    # Check AI session first
    ai_session = context.bot_data.get("ai_sessions", {}).get(user_id)
    if ai_session and ai_session.get("active"):
        await handle_ai_text(update, context)
        return
    
    # Otherwise, fall through to main1's handler
    from main1 import handle_text_message
    await handle_text_message(update, context)


async def master_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master photo handler - routes to AI or upload handlers."""
    if not update.message or not update.message.from_user:
        return
    
    user_id = update.message.from_user.id
    
    # Check AI session first
    ai_session = context.bot_data.get("ai_sessions", {}).get(user_id)
    if ai_session and ai_session.get("active"):
        handled = await handle_ai_image(update, context)
        if handled:
            return
    
    # Otherwise, fall through to upload handler
    from main1 import handle_file_upload
    await handle_file_upload(update, context)


async def master_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master file handler - routes to AI (if image) or upload handlers."""
    if not update.message or not update.message.from_user:
        return
    
    user_id = update.message.from_user.id
    
    # Check AI session - if document is an image, process with AI
    ai_session = context.bot_data.get("ai_sessions", {}).get(user_id)
    if ai_session and ai_session.get("active"):
        if (update.message.document and 
            update.message.document.mime_type and 
            update.message.document.mime_type.startswith("image/")):
            handled = await handle_ai_image(update, context)
            if handled:
                return
    
    # Otherwise, fall through to upload handler
    from main1 import handle_file_upload
    await handle_file_upload(update, context)


# ═══════════════════════════════════════════
# REGISTER ALL HANDLERS
# ═══════════════════════════════════════════

def register_handlers(app):
    """Register all main2 (AI) handlers."""
    
    # Commands
    app.add_handler(CommandHandler("ai", cmd_ai))
    app.add_handler(CommandHandler("exitai", cmd_exitai))
    
    # AI Callback queries
    app.add_handler(CallbackQueryHandler(start_ai_chat, pattern="^menu_ai$"))
    app.add_handler(CallbackQueryHandler(ai_exit_callback, pattern="^ai_exit$"))
    app.add_handler(CallbackQueryHandler(ai_clear_callback, pattern="^ai_clear$"))
    app.add_handler(CallbackQueryHandler(ai_retry_callback, pattern="^ai_retry$"))
    
    # IMPORTANT: Remove main1's handlers for text and files, replace with master handlers
    # We need to remove the previously registered handlers and add our master ones
    
    # Remove conflicting handlers from main1
    handlers_to_remove = []
    for group_handlers in app.handlers.values():
        for handler in group_handlers:
            if isinstance(handler, MessageHandler):
                if handler.callback.__name__ in ('handle_text_message', 'handle_file_upload'):
                    handlers_to_remove.append((0, handler))
    
    for group, handler in handlers_to_remove:
        try:
            app.remove_handler(handler, group)
        except Exception:
            pass
    
    # Add master handlers that route between AI and storage
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        master_text_handler
    ))
    
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.ChatType.PRIVATE,
        master_photo_handler
    ))
    
    app.add_handler(MessageHandler(
        (filters.Document.ALL | filters.VIDEO | filters.AUDIO | 
         filters.VOICE | filters.VIDEO_NOTE | filters.Sticker.ALL | 
         filters.ANIMATION) & filters.ChatType.PRIVATE,
        master_file_handler
    ))
    
    logger.info("Main2 handlers registered: AI Chat (Gemini)")
