import logging
import os
import json
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ForumTopic, BotCommand
)
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ConversationHandler
)
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# ─── File type mappings ───
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.tiff', '.ico', '.heic', '.heif'}
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp'}
ZIP_EXTENSIONS = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.tar.gz', '.tar.bz2', '.tar.xz'}

TOPIC_NAMES = ["IMAGE_UPLOAD", "VIDEO_UPLOAD", "ZIP_UPLOAD", "FILE_UPLOAD"]

PERSISTENCE_FILE = "bot_data.json"


def save_persistent_data(bot_data):
    """Save critical bot_data to a JSON file."""
    data = {
        "STORAGE_CHAT_ID": bot_data.get("STORAGE_CHAT_ID"),
        "topics": bot_data.get("topics", {}),
        "file_index": bot_data.get("file_index", []),
    }
    try:
        with open(PERSISTENCE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save persistent data: {e}")


def load_persistent_data(bot_data):
    """Load saved data if exists."""
    if os.path.exists(PERSISTENCE_FILE):
        try:
            with open(PERSISTENCE_FILE, "r") as f:
                data = json.load(f)
            bot_data["STORAGE_CHAT_ID"] = data.get("STORAGE_CHAT_ID")
            bot_data["topics"] = data.get("topics", {})
            bot_data["file_index"] = data.get("file_index", [])
            logger.info(f"Loaded persistent data: storage={bot_data['STORAGE_CHAT_ID']}, topics={list(bot_data['topics'].keys())}, files={len(bot_data['file_index'])}")
        except Exception as e:
            logger.error(f"Failed to load persistent data: {e}")


def get_file_category(filename: str) -> str:
    """Determine which topic a file belongs to based on extension."""
    if not filename:
        return "FILE_UPLOAD"
    lower = filename.lower()
    for ext in IMAGE_EXTENSIONS:
        if lower.endswith(ext):
            return "IMAGE_UPLOAD"
    for ext in VIDEO_EXTENSIONS:
        if lower.endswith(ext):
            return "VIDEO_UPLOAD"
    for ext in ZIP_EXTENSIONS:
        if lower.endswith(ext):
            return "ZIP_UPLOAD"
    return "FILE_UPLOAD"


def get_extension_category(ext: str) -> str:
    """Given an extension string, return which topic to search."""
    ext_dot = ext if ext.startswith('.') else f'.{ext}'
    ext_dot = ext_dot.lower()
    if ext_dot in IMAGE_EXTENSIONS:
        return "IMAGE_UPLOAD"
    if ext_dot in VIDEO_EXTENSIONS:
        return "VIDEO_UPLOAD"
    if ext_dot in ZIP_EXTENSIONS:
        return "ZIP_UPLOAD"
    return None  # Search all


def get_main_menu_keyboard():
    """Return the main menu inline keyboard."""
    keyboard = [
        [InlineKeyboardButton("📤 Upload", callback_data="menu_upload"),
         InlineKeyboardButton("🔍 Search", callback_data="menu_search")],
        [InlineKeyboardButton("🤖 AI Chat", callback_data="menu_ai")],
        [InlineKeyboardButton("⚙️ Setup Storage", callback_data="menu_setup"),
         InlineKeyboardButton("📊 Stats", callback_data="menu_stats")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ═══════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start and /menu commands."""
    load_persistent_data(context.bot_data)
    
    storage_id = context.bot_data.get("STORAGE_CHAT_ID")
    topics = context.bot_data.get("topics", {})
    file_count = len(context.bot_data.get("file_index", []))
    
    status = "✅ Connected" if storage_id else "❌ Not set"
    topics_status = "✅ Ready" if len(topics) == 4 else f"⚠️ {len(topics)}/4"
    
    text = (
        "🤖 <b>Super Main Bot</b>\n\n"
        f"📦 Storage: {status}\n"
        f"📂 Topics: {topics_status}\n"
        f"📁 Indexed Files: {file_count}\n\n"
        "Choose an option below:"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu_keyboard())


async def cmd_setstorage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set the storage group chat ID. Usage: /setstorage <chat_id>"""
    if not context.args:
        await update.message.reply_text(
            "Usage: `/setstorage <chat_id>`\n\n"
            "To get your group chat ID:\n"
            "1. Add the bot to your MyStorage group\n"
            "2. Send a message in the group\n"
            "3. Forward that message to @userinfobot or check logs\n\n"
            "Or use /setupstorage to auto-detect.",
            parse_mode="Markdown"
        )
        return
    
    try:
        chat_id = int(context.args[0])
        context.bot_data["STORAGE_CHAT_ID"] = chat_id
        save_persistent_data(context.bot_data)
        await update.message.reply_text(f"✅ Storage chat ID set to: `{chat_id}`", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Invalid chat ID. Must be a number.")


async def cmd_createtopics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create the 4 required topics in the storage group."""
    storage_id = context.bot_data.get("STORAGE_CHAT_ID")
    if not storage_id:
        await update.message.reply_text("❌ Storage not set. Use /setstorage first.")
        return
    
    status_msg = await update.message.reply_text("⏳ Creating topics...")
    
    topic_icons = {
        "IMAGE_UPLOAD": "📷",
        "VIDEO_UPLOAD": "🎬",
        "ZIP_UPLOAD": "📦",
        "FILE_UPLOAD": "📄"
    }
    
    # Icon color IDs for forum topics (Telegram requires one of these)
    # 7322096 = blue, 16766590 = yellow, 13338331 = purple,
    # 9367192 = green, 16749490 = red, 16478047 = orange
    icon_colors = {
        "IMAGE_UPLOAD": 16749490,   # red
        "VIDEO_UPLOAD": 13338331,   # purple
        "ZIP_UPLOAD": 9367192,      # green
        "FILE_UPLOAD": 7322096,     # blue
    }
    
    created = []
    existing = context.bot_data.get("topics", {})
    
    for name in TOPIC_NAMES:
        if name in existing:
            created.append(f"⏭️ {name} (already exists)")
            continue
        try:
            topic: ForumTopic = await context.bot.create_forum_topic(
                chat_id=storage_id,
                name=name,
                icon_color=icon_colors.get(name, 7322096)
            )
            context.bot_data["topics"][name] = topic.message_thread_id
            created.append(f"✅ {topic_icons.get(name, '📁')} {name} (ID: {topic.message_thread_id})")
        except Exception as e:
            created.append(f"❌ {name}: {str(e)}")
            logger.error(f"Failed to create topic {name}: {e}")
    
    save_persistent_data(context.bot_data)
    
    result = "\n".join(created)
    await status_msg.edit_text(f"📂 <b>Topic Creation Results:</b>\n\n{result}", parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════
# UPLOAD SYSTEM
# ═══════════════════════════════════════════

async def start_upload_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start an upload session - user sends files, then confirms."""
    query = update.callback_query
    if query:
        await query.answer()
    
    storage_id = context.bot_data.get("STORAGE_CHAT_ID")
    topics = context.bot_data.get("topics", {})
    
    if not storage_id or len(topics) < 4:
        msg = "❌ Storage not configured. Use ⚙️ Setup first."
        if query:
            await query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return
    
    user_id = query.from_user.id if query else update.message.from_user.id
    
    # Initialize upload session
    context.bot_data["upload_sessions"][user_id] = {
        "files": [],
        "active": True
    }
    
    keyboard = [
        [InlineKeyboardButton("✅ Done - Upload All", callback_data="upload_done")],
        [InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")],
    ]
    
    text = (
        "📤 <b>Upload Session Started!</b>\n\n"
        "Send me your files now. I accept:\n"
        "• 📷 Images (jpg, png, gif, etc.)\n"
        "• 🎬 Videos (mp4, avi, mkv, etc.)\n"
        "• 📦 Archives (zip, rar, 7z, etc.)\n"
        "• 📄 Any other files\n\n"
        "Files received: <b>0</b>\n\n"
        "When done, press <b>✅ Done</b> or type /done\n"
        "To cancel, press <b>❌ Cancel</b>"
    )
    
    if query:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming files during an upload session."""
    user_id = update.message.from_user.id
    session = context.bot_data.get("upload_sessions", {}).get(user_id)
    
    if not session or not session.get("active"):
        return  # No active session, ignore
    
    message = update.message
    file_info = None
    
    if message.document:
        doc = message.document
        file_info = {
            "file_id": doc.file_id,
            "file_name": doc.file_name or "unknown_file",
            "file_size": doc.file_size,
            "mime_type": doc.mime_type or "",
            "type": "document"
        }
    elif message.photo:
        # Get highest resolution photo
        photo = message.photo[-1]
        file_info = {
            "file_id": photo.file_id,
            "file_name": f"photo_{photo.file_unique_id}.jpg",
            "file_size": photo.file_size,
            "mime_type": "image/jpeg",
            "type": "photo"
        }
    elif message.video:
        vid = message.video
        file_info = {
            "file_id": vid.file_id,
            "file_name": vid.file_name or f"video_{vid.file_unique_id}.mp4",
            "file_size": vid.file_size,
            "mime_type": vid.mime_type or "video/mp4",
            "type": "video"
        }
    elif message.animation:
        anim = message.animation
        file_info = {
            "file_id": anim.file_id,
            "file_name": anim.file_name or f"animation_{anim.file_unique_id}.gif",
            "file_size": anim.file_size,
            "mime_type": anim.mime_type or "image/gif",
            "type": "animation"
        }
    elif message.audio:
        aud = message.audio
        file_info = {
            "file_id": aud.file_id,
            "file_name": aud.file_name or f"audio_{aud.file_unique_id}.mp3",
            "file_size": aud.file_size,
            "mime_type": aud.mime_type or "audio/mpeg",
            "type": "audio"
        }
    elif message.voice:
        voice = message.voice
        file_info = {
            "file_id": voice.file_id,
            "file_name": f"voice_{voice.file_unique_id}.ogg",
            "file_size": voice.file_size,
            "mime_type": voice.mime_type or "audio/ogg",
            "type": "voice"
        }
    elif message.video_note:
        vn = message.video_note
        file_info = {
            "file_id": vn.file_id,
            "file_name": f"videonote_{vn.file_unique_id}.mp4",
            "file_size": vn.file_size,
            "mime_type": "video/mp4",
            "type": "video_note"
        }
    elif message.sticker:
        stk = message.sticker
        ext = ".webp" if not stk.is_animated and not stk.is_video else ".tgs" if stk.is_animated else ".webm"
        file_info = {
            "file_id": stk.file_id,
            "file_name": f"sticker_{stk.file_unique_id}{ext}",
            "file_size": stk.file_size,
            "mime_type": "image/webp",
            "type": "sticker"
        }
    
    if file_info:
        session["files"].append(file_info)
        count = len(session["files"])
        
        # Determine category
        category = get_file_category(file_info["file_name"])
        cat_emoji = {"IMAGE_UPLOAD": "📷", "VIDEO_UPLOAD": "🎬", "ZIP_UPLOAD": "📦", "FILE_UPLOAD": "📄"}.get(category, "📁")
        
        keyboard = [
            [InlineKeyboardButton("✅ Done - Upload All", callback_data="upload_done")],
            [InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")],
        ]
        
        await message.reply_text(
            f"{cat_emoji} File received: <b>{file_info['file_name']}</b>\n"
            f"Category: <b>{category}</b>\n"
            f"Total files in session: <b>{count}</b>\n\n"
            f"Send more files or press Done.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /done command to finish upload session."""
    user_id = update.message.from_user.id
    session = context.bot_data.get("upload_sessions", {}).get(user_id)
    
    if not session or not session.get("active"):
        await update.message.reply_text("❌ No active upload session. Use /menu to start one.")
        return
    
    await _process_upload(update, context, user_id, is_callback=False)


async def upload_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the Done button press."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    session = context.bot_data.get("upload_sessions", {}).get(user_id)
    
    if not session or not session.get("active"):
        await query.edit_message_text("❌ No active upload session.")
        return
    
    await _process_upload(update, context, user_id, is_callback=True)


async def _process_upload(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, is_callback: bool):
    """Process and forward all files in the upload session to appropriate topics."""
    session = context.bot_data["upload_sessions"][user_id]
    files = session["files"]
    
    if not files:
        msg = "❌ No files to upload. Session cancelled."
        if is_callback:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        del context.bot_data["upload_sessions"][user_id]
        return
    
    # Mark session as inactive
    session["active"] = False
    
    storage_id = context.bot_data["STORAGE_CHAT_ID"]
    topics = context.bot_data["topics"]
    
    if is_callback:
        status_msg = await update.callback_query.edit_message_text(
            f"⏳ Uploading {len(files)} file(s) to storage..."
        )
    else:
        status_msg = await update.message.reply_text(
            f"⏳ Uploading {len(files)} file(s) to storage..."
        )
    
    results = {"success": 0, "fail": 0, "details": []}
    
    for f in files:
        category = get_file_category(f["file_name"])
        topic_id = topics.get(category)
        
        if not topic_id:
            results["fail"] += 1
            results["details"].append(f"❌ {f['file_name']} - Topic {category} not found")
            continue
        
        try:
            caption = f"📁 {f['file_name']}"
            
            sent_msg = None
            if f["type"] == "photo":
                sent_msg = await context.bot.send_photo(
                    chat_id=storage_id,
                    message_thread_id=topic_id,
                    photo=f["file_id"],
                    caption=caption
                )
            elif f["type"] == "video" or f["type"] == "video_note":
                sent_msg = await context.bot.send_video(
                    chat_id=storage_id,
                    message_thread_id=topic_id,
                    video=f["file_id"],
                    caption=caption
                )
            elif f["type"] == "animation":
                sent_msg = await context.bot.send_animation(
                    chat_id=storage_id,
                    message_thread_id=topic_id,
                    animation=f["file_id"],
                    caption=caption
                )
            elif f["type"] == "audio":
                sent_msg = await context.bot.send_audio(
                    chat_id=storage_id,
                    message_thread_id=topic_id,
                    audio=f["file_id"],
                    caption=caption
                )
            elif f["type"] == "voice":
                sent_msg = await context.bot.send_voice(
                    chat_id=storage_id,
                    message_thread_id=topic_id,
                    voice=f["file_id"],
                    caption=caption
                )
            else:
                sent_msg = await context.bot.send_document(
                    chat_id=storage_id,
                    message_thread_id=topic_id,
                    document=f["file_id"],
                    caption=caption
                )
            
            # Index the file
            index_entry = {
                "file_name": f["file_name"],
                "file_id": f["file_id"],
                "category": category,
                "topic_id": topic_id,
                "message_id": sent_msg.message_id if sent_msg else None,
                "mime_type": f.get("mime_type", ""),
                "file_size": f.get("file_size", 0),
                "type": f["type"],
                "uploaded_by": user_id
            }
            context.bot_data["file_index"].append(index_entry)
            
            results["success"] += 1
            cat_emoji = {"IMAGE_UPLOAD": "📷", "VIDEO_UPLOAD": "🎬", "ZIP_UPLOAD": "📦", "FILE_UPLOAD": "📄"}.get(category, "📁")
            results["details"].append(f"✅ {cat_emoji} {f['file_name']} → {category}")
            
        except Exception as e:
            results["fail"] += 1
            results["details"].append(f"❌ {f['file_name']} - Error: {str(e)[:50]}")
            logger.error(f"Upload error for {f['file_name']}: {e}")
    
    # Save index
    save_persistent_data(context.bot_data)
    
    # Clean up session
    del context.bot_data["upload_sessions"][user_id]
    
    detail_text = "\n".join(results["details"][:20])  # Limit to 20 lines
    if len(results["details"]) > 20:
        detail_text += f"\n... and {len(results['details']) - 20} more"
    
    keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
    
    await status_msg.edit_text(
        f"📤 <b>Upload Complete!</b>\n\n"
        f"✅ Success: {results['success']}\n"
        f"❌ Failed: {results['fail']}\n\n"
        f"<b>Details:</b>\n{detail_text}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def upload_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the upload session."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id in context.bot_data.get("upload_sessions", {}):
        del context.bot_data["upload_sessions"][user_id]
    
    keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
    await query.edit_message_text("❌ Upload session cancelled.", reply_markup=InlineKeyboardMarkup(keyboard))


# ═══════════════════════════════════════════
# SEARCH SYSTEM
# ═══════════════════════════════════════════

async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the search interface."""
    query = update.callback_query
    if query:
        await query.answer()
    
    file_count = len(context.bot_data.get("file_index", []))
    
    keyboard = [
        [InlineKeyboardButton("📝 Search by Name", callback_data="search_byname")],
        [InlineKeyboardButton("📂 Search by File Type", callback_data="search_bytype")],
        [InlineKeyboardButton("📋 List All Files", callback_data="search_listall")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
    ]
    
    text = (
        f"🔍 <b>Search Files</b>\n\n"
        f"📁 Total indexed files: <b>{file_count}</b>\n\n"
        f"Choose search mode:"
    )
    
    if query:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def search_byname_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt user to enter search term."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    context.bot_data.setdefault("search_sessions", {})[user_id] = {"mode": "name"}
    
    keyboard = [[InlineKeyboardButton("❌ Cancel Search", callback_data="menu_search")]]
    await query.edit_message_text(
        "🔍 <b>Search by Name</b>\n\n"
        "Type the name (or part of the name) you want to search for.\n"
        "Example: <code>picture</code> or <code>document</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def search_bytype_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt user to enter file type."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    context.bot_data.setdefault("search_sessions", {})[user_id] = {"mode": "type"}
    
    keyboard = [
        [InlineKeyboardButton("📷 Images", callback_data="searchtype_image"),
         InlineKeyboardButton("🎬 Videos", callback_data="searchtype_video")],
        [InlineKeyboardButton("📦 Archives", callback_data="searchtype_zip"),
         InlineKeyboardButton("📄 Documents", callback_data="searchtype_file")],
        [InlineKeyboardButton("✏️ Enter Extension", callback_data="searchtype_custom")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu_search")],
    ]
    
    await query.edit_message_text(
        "🔍 <b>Search by File Type</b>\n\n"
        "Choose a category or enter a custom extension:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def search_by_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search files by predefined category."""
    query = update.callback_query
    await query.answer()
    
    category_map = {
        "searchtype_image": "IMAGE_UPLOAD",
        "searchtype_video": "VIDEO_UPLOAD",
        "searchtype_zip": "ZIP_UPLOAD",
        "searchtype_file": "FILE_UPLOAD"
    }
    
    category = category_map.get(query.data)
    if not category:
        return
    
    file_index = context.bot_data.get("file_index", [])
    results = [f for f in file_index if f["category"] == category]
    
    await _send_search_results(query, results, f"Category: {category}")


async def searchtype_custom_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt for custom extension."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    context.bot_data.setdefault("search_sessions", {})[user_id] = {"mode": "extension"}
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="search_bytype")]]
    await query.edit_message_text(
        "🔍 <b>Search by Extension</b>\n\n"
        "Type the file extension you want to search for.\n"
        "Example: <code>png</code>, <code>mp4</code>, <code>pdf</code>, <code>zip</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for search (both name and extension mode)."""
    user_id = update.message.from_user.id
    search_session = context.bot_data.get("search_sessions", {}).get(user_id)
    
    if not search_session:
        return  # Not in search mode
    
    query_text = update.message.text.strip().lower()
    file_index = context.bot_data.get("file_index", [])
    mode = search_session.get("mode")
    
    if mode == "name":
        results = [f for f in file_index if query_text in f["file_name"].lower()]
        title = f"Name: \"{query_text}\""
    elif mode == "extension":
        ext = query_text if query_text.startswith('.') else f'.{query_text}'
        
        # Smart: check which category this extension belongs to
        target_category = get_extension_category(ext)
        
        if target_category:
            # Smart search: only look in the relevant category
            results = [f for f in file_index 
                      if f["category"] == target_category and f["file_name"].lower().endswith(ext)]
        else:
            # Search everywhere
            results = [f for f in file_index if f["file_name"].lower().endswith(ext)]
        
        title = f"Extension: {ext}"
        if target_category:
            title += f" (Smart: searched in {target_category})"
    elif mode == "type":
        results = [f for f in file_index if query_text in f.get("mime_type", "").lower()]
        title = f"MIME type: \"{query_text}\""
    else:
        return
    
    # Clean up search session
    del context.bot_data["search_sessions"][user_id]
    
    await _send_search_results_message(update.message, results, title, context)


async def _send_search_results(query, results, title):
    """Send search results from a callback query."""
    if not results:
        keyboard = [[InlineKeyboardButton("🔙 Search Again", callback_data="menu_search")],
                     [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
        await query.edit_message_text(
            f"🔍 <b>Search Results - {title}</b>\n\n"
            f"❌ No files found.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    cat_emoji = {"IMAGE_UPLOAD": "📷", "VIDEO_UPLOAD": "🎬", "ZIP_UPLOAD": "📦", "FILE_UPLOAD": "📄"}
    
    lines = []
    for i, f in enumerate(results[:30], 1):
        emoji = cat_emoji.get(f["category"], "📁")
        size = _format_size(f.get("file_size", 0))
        lines.append(f"{i}. {emoji} <code>{f['file_name']}</code> ({size})")
    
    text = f"🔍 <b>Search Results - {title}</b>\n\n"
    text += f"Found: <b>{len(results)}</b> file(s)\n\n"
    text += "\n".join(lines)
    
    if len(results) > 30:
        text += f"\n\n... and {len(results) - 30} more files"
    
    # Add buttons to retrieve files
    keyboard = []
    for i, f in enumerate(results[:10]):
        keyboard.append([InlineKeyboardButton(
            f"📥 {f['file_name'][:30]}", 
            callback_data=f"getfile_{i}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Search Again", callback_data="menu_search")])
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
    
    # Store results temporarily for file retrieval
    # We use a special key in bot_data
    query_user_id = query.from_user.id
    
    # Can't easily pass results through callback, so we'll store them
    # This is a simplification - in production you'd use a proper cache
    
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def _send_search_results_message(message, results, title, context):
    """Send search results from a regular message."""
    if not results:
        keyboard = [[InlineKeyboardButton("🔙 Search Again", callback_data="menu_search")],
                     [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
        await message.reply_text(
            f"🔍 <b>Search Results - {title}</b>\n\n"
            f"❌ No files found.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    cat_emoji = {"IMAGE_UPLOAD": "📷", "VIDEO_UPLOAD": "🎬", "ZIP_UPLOAD": "📦", "FILE_UPLOAD": "📄"}
    
    lines = []
    for i, f in enumerate(results[:30], 1):
        emoji = cat_emoji.get(f["category"], "📁")
        size = _format_size(f.get("file_size", 0))
        lines.append(f"{i}. {emoji} <code>{f['file_name']}</code> ({size})")
    
    text = f"🔍 <b>Search Results - {title}</b>\n\n"
    text += f"Found: <b>{len(results)}</b> file(s)\n\n"
    text += "\n".join(lines)
    
    if len(results) > 30:
        text += f"\n\n... and {len(results) - 30} more files"
    
    # Store search results for retrieval
    user_id = message.from_user.id
    context.bot_data.setdefault("search_results", {})[user_id] = results
    
    keyboard = []
    for i, f in enumerate(results[:10]):
        keyboard.append([InlineKeyboardButton(
            f"📥 {f['file_name'][:30]}", 
            callback_data=f"getfile_{i}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Search Again", callback_data="menu_search")])
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
    
    await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def getfile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a specific file to the user from search results."""
    query = update.callback_query
    await query.answer("📥 Sending file...")
    
    user_id = query.from_user.id
    index = int(query.data.split("_")[1])
    
    # Try to get from stored search results
    results = context.bot_data.get("search_results", {}).get(user_id, [])
    
    if not results:
        # Fallback: try from file_index
        file_index = context.bot_data.get("file_index", [])
        if index < len(file_index):
            file_entry = file_index[index]
        else:
            await query.answer("❌ File not found", show_alert=True)
            return
    else:
        if index < len(results):
            file_entry = results[index]
        else:
            await query.answer("❌ File not found", show_alert=True)
            return
    
    try:
        f_type = file_entry.get("type", "document")
        caption = f"📁 {file_entry['file_name']}"
        
        if f_type == "photo":
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=file_entry["file_id"], caption=caption)
        elif f_type in ("video", "video_note"):
            await context.bot.send_video(chat_id=query.message.chat_id, video=file_entry["file_id"], caption=caption)
        elif f_type == "animation":
            await context.bot.send_animation(chat_id=query.message.chat_id, animation=file_entry["file_id"], caption=caption)
        elif f_type == "audio":
            await context.bot.send_audio(chat_id=query.message.chat_id, audio=file_entry["file_id"], caption=caption)
        elif f_type == "voice":
            await context.bot.send_voice(chat_id=query.message.chat_id, voice=file_entry["file_id"], caption=caption)
        else:
            await context.bot.send_document(chat_id=query.message.chat_id, document=file_entry["file_id"], caption=caption)
    except Exception as e:
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Error sending file: {str(e)[:100]}")


async def search_listall_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all indexed files."""
    query = update.callback_query
    await query.answer()
    
    file_index = context.bot_data.get("file_index", [])
    
    # Store results for retrieval
    user_id = query.from_user.id
    context.bot_data.setdefault("search_results", {})[user_id] = file_index
    
    await _send_search_results(query, file_index, "All Files")


# ═══════════════════════════════════════════
# SETUP & UTILITY
# ═══════════════════════════════════════════

async def setup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Setup storage configuration."""
    query = update.callback_query
    await query.answer()
    
    storage_id = context.bot_data.get("STORAGE_CHAT_ID")
    topics = context.bot_data.get("topics", {})
    
    keyboard = []
    
    if not storage_id:
        keyboard.append([InlineKeyboardButton("📝 Set Storage ID", callback_data="setup_setid")])
    else:
        keyboard.append([InlineKeyboardButton(f"✅ Storage: {storage_id}", callback_data="setup_setid")])
        if len(topics) < 4:
            keyboard.append([InlineKeyboardButton("📂 Create Topics", callback_data="setup_createtopics")])
        else:
            keyboard.append([InlineKeyboardButton("✅ Topics: All Created", callback_data="noop")])
    
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="menu_setup")])
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
    
    topic_list = "\n".join([f"  • {name}: {tid}" for name, tid in topics.items()]) or "  None created"
    
    await query.edit_message_text(
        f"⚙️ <b>Storage Setup</b>\n\n"
        f"Storage Chat ID: <code>{storage_id or 'Not set'}</code>\n\n"
        f"Topics:\n{topic_list}\n\n"
        f"To set storage ID, send:\n<code>/setstorage YOUR_CHAT_ID</code>\n\n"
        f"Add the bot to your group, then forward any message from the group to @userinfobot to get the chat ID.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def setup_createtopics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create topics via callback button."""
    query = update.callback_query
    await query.answer("Creating topics...")
    
    storage_id = context.bot_data.get("STORAGE_CHAT_ID")
    if not storage_id:
        await query.edit_message_text("❌ Set storage ID first!")
        return
    
    icon_colors = {
        "IMAGE_UPLOAD": 16749490,
        "VIDEO_UPLOAD": 13338331,
        "ZIP_UPLOAD": 9367192,
        "FILE_UPLOAD": 7322096,
    }
    
    created = []
    existing = context.bot_data.get("topics", {})
    
    for name in TOPIC_NAMES:
        if name in existing:
            created.append(f"⏭️ {name} (exists)")
            continue
        try:
            topic = await context.bot.create_forum_topic(
                chat_id=storage_id,
                name=name,
                icon_color=icon_colors.get(name, 7322096)
            )
            context.bot_data["topics"][name] = topic.message_thread_id
            created.append(f"✅ {name}")
        except Exception as e:
            created.append(f"❌ {name}: {str(e)[:40]}")
    
    save_persistent_data(context.bot_data)
    
    keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
    await query.edit_message_text(
        f"📂 <b>Topics Created:</b>\n\n" + "\n".join(created),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show storage statistics."""
    query = update.callback_query
    await query.answer()
    
    file_index = context.bot_data.get("file_index", [])
    
    cat_counts = {}
    total_size = 0
    for f in file_index:
        cat = f.get("category", "unknown")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        total_size += f.get("file_size", 0) or 0
    
    cat_emoji = {"IMAGE_UPLOAD": "📷", "VIDEO_UPLOAD": "🎬", "ZIP_UPLOAD": "📦", "FILE_UPLOAD": "📄"}
    
    lines = []
    for cat in TOPIC_NAMES:
        count = cat_counts.get(cat, 0)
        emoji = cat_emoji.get(cat, "📁")
        lines.append(f"{emoji} {cat}: <b>{count}</b>")
    
    keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
    
    await query.edit_message_text(
        f"📊 <b>Storage Statistics</b>\n\n"
        f"📁 Total Files: <b>{len(file_index)}</b>\n"
        f"💾 Total Size: <b>{_format_size(total_size)}</b>\n\n"
        + "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu."""
    query = update.callback_query
    await query.answer()
    
    storage_id = context.bot_data.get("STORAGE_CHAT_ID")
    topics = context.bot_data.get("topics", {})
    file_count = len(context.bot_data.get("file_index", []))
    
    status = "✅ Connected" if storage_id else "❌ Not set"
    topics_status = "✅ Ready" if len(topics) == 4 else f"⚠️ {len(topics)}/4"
    
    text = (
        "🤖 <b>Super Main Bot</b>\n\n"
        f"📦 Storage: {status}\n"
        f"📂 Topics: {topics_status}\n"
        f"📁 Indexed Files: {file_count}\n\n"
        "Choose an option below:"
    )
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu_keyboard())


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """No-op callback for informational buttons."""
    await update.callback_query.answer()


def _format_size(size_bytes):
    """Format bytes to human readable."""
    if not size_bytes:
        return "Unknown"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# ═══════════════════════════════════════════
# MESSAGE ROUTER - handles text that could be search or regular
# ═══════════════════════════════════════════

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route text messages - check if user is in a search session."""
    user_id = update.message.from_user.id
    
    # Check for active search session
    search_session = context.bot_data.get("search_sessions", {}).get(user_id)
    if search_session:
        await handle_search_input(update, context)
        return
    
    # Check for active upload session (user sent text instead of file)
    upload_session = context.bot_data.get("upload_sessions", {}).get(user_id)
    if upload_session and upload_session.get("active"):
        await update.message.reply_text(
            "📤 You're in an upload session. Send files, not text!\n"
            "Press ✅ Done when finished or ❌ Cancel to abort."
        )
        return


# ═══════════════════════════════════════════
# AUTO-DETECT STORAGE GROUP
# ═══════════════════════════════════════════

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-detect when bot is used in a group - capture chat ID."""
    if update.message and update.message.chat.type in ("group", "supergroup"):
        chat_id = update.message.chat_id
        chat_title = update.message.chat.title
        
        if not context.bot_data.get("STORAGE_CHAT_ID"):
            # Check if this might be our storage group
            if "storage" in (chat_title or "").lower() or "mystorage" in (chat_title or "").lower():
                context.bot_data["STORAGE_CHAT_ID"] = chat_id
                save_persistent_data(context.bot_data)
                logger.info(f"Auto-detected storage group: {chat_title} ({chat_id})")


# ═══════════════════════════════════════════
# REGISTER ALL HANDLERS
# ═══════════════════════════════════════════

def register_handlers(app):
    """Register all main1 handlers."""
    
    # Load persistent data on startup
    load_persistent_data(app.bot_data)
    
    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_start))
    app.add_handler(CommandHandler("setstorage", cmd_setstorage))
    app.add_handler(CommandHandler("createtopics", cmd_createtopics))
    app.add_handler(CommandHandler("done", cmd_done))
    
    # Callback queries - Main Menu
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(noop_callback, pattern="^noop$"))
    
    # Callback queries - Upload
    app.add_handler(CallbackQueryHandler(start_upload_session, pattern="^menu_upload$"))
    app.add_handler(CallbackQueryHandler(upload_done_callback, pattern="^upload_done$"))
    app.add_handler(CallbackQueryHandler(upload_cancel_callback, pattern="^upload_cancel$"))
    
    # Callback queries - Search
    app.add_handler(CallbackQueryHandler(start_search, pattern="^menu_search$"))
    app.add_handler(CallbackQueryHandler(search_byname_start, pattern="^search_byname$"))
    app.add_handler(CallbackQueryHandler(search_bytype_start, pattern="^search_bytype$"))
    app.add_handler(CallbackQueryHandler(search_listall_callback, pattern="^search_listall$"))
    app.add_handler(CallbackQueryHandler(search_by_category_callback, pattern="^searchtype_(image|video|zip|file)$"))
    app.add_handler(CallbackQueryHandler(searchtype_custom_callback, pattern="^searchtype_custom$"))
    app.add_handler(CallbackQueryHandler(getfile_callback, pattern=r"^getfile_\d+$"))
    
    # Callback queries - Setup
    app.add_handler(CallbackQueryHandler(setup_callback, pattern="^menu_setup$"))
    app.add_handler(CallbackQueryHandler(setup_createtopics_callback, pattern="^setup_createtopics$"))
    app.add_handler(CallbackQueryHandler(stats_callback, pattern="^menu_stats$"))
    
    # File handler (for upload sessions) - catches all file types
    app.add_handler(MessageHandler(
        filters.ATTACHMENT & filters.ChatType.PRIVATE,
        handle_file_upload
    ))
    
    # Text handler for search input and general routing
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_text_message
    ))
    
    # Group message handler for auto-detection
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS,
        handle_group_message
    ))
    
    logger.info("Main1 handlers registered: Storage, Upload, Search")
