import logging
import os
import json
from github import Github
from github.GithubException import UnknownObjectException
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ForumTopic
)
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# ─── File type mappings ───
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.tiff', '.ico', '.heic', '.heif'}
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp'}
ZIP_EXTENSIONS = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.tar.gz', '.tar.bz2', '.tar.xz'}

TOPIC_NAMES = ["IMAGE_UPLOAD", "VIDEO_UPLOAD", "ZIP_UPLOAD", "FILE_UPLOAD"]


# ═══════════════════════════════════════════
# GITHUB DATABASE SYSTEM
# ═══════════════════════════════════════════

def save_to_github(bot_data):
    """Save critical bot_data directly to a GitHub repository."""
    token = bot_data.get("GITHUB_TOKEN")
    repo_name = bot_data.get("GITHUB_REPO")
    
    if not token or not repo_name:
        logger.error("GitHub Token or Repo not set. Cannot save DB.")
        return

    try:
        g = Github(token)
        repo = g.get_repo(repo_name)
        file_path = "database.json"
        
        data = {
            "STORAGE_CHAT_ID": bot_data.get("STORAGE_CHAT_ID"),
            "topics": bot_data.get("topics", {}),
            "file_index": bot_data.get("file_index", []),
        }
        content = json.dumps(data, indent=2)
        
        try:
            file = repo.get_contents(file_path)
            repo.update_file(file_path, "Automated DB Update", content, file.sha)
            logger.info("Successfully updated database.json on GitHub.")
        except UnknownObjectException:
            repo.create_file(file_path, "Initialize DB", content)
            logger.info("Successfully created database.json on GitHub.")
    except Exception as e:
        logger.error(f"Failed to save to GitHub: {e}")


def load_from_github(bot_data):
    """Load saved data from GitHub repository."""
    token = bot_data.get("GITHUB_TOKEN")
    repo_name = bot_data.get("GITHUB_REPO")
    
    if not token or not repo_name:
        return

    try:
        g = Github(token)
        repo = g.get_repo(repo_name)
        file = repo.get_contents("database.json")
        data = json.loads(file.decoded_content.decode("utf-8"))
        
        bot_data["STORAGE_CHAT_ID"] = data.get("STORAGE_CHAT_ID")
        bot_data["topics"] = data.get("topics", {})
        bot_data["file_index"] = data.get("file_index", [])
        logger.info(f"Loaded GitHub DB: storage={bot_data['STORAGE_CHAT_ID']}, files={len(bot_data['file_index'])}")
    except UnknownObjectException:
        logger.info("No database.json found on GitHub yet. Starting fresh.")
    except Exception as e:
        logger.error(f"Failed to load from GitHub: {e}")


# ═══════════════════════════════════════════
# UTILITIES & UI CLEANUP
# ═══════════════════════════════════════════

async def clean_ui(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes the user's command message and the old bot menu to keep chat clean."""
    # 1. Try to delete the user's command (e.g., /menu)
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass

    # 2. Try to delete the last menu sent by the bot
    if "last_menu_id" in context.user_data:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id, 
                message_id=context.user_data["last_menu_id"]
            )
        except Exception:
            pass


def get_file_category(filename: str) -> str:
    """Determine which topic a file belongs to based on extension."""
    if not filename:
        return "FILE_UPLOAD"
    lower = filename.lower()
    for ext in IMAGE_EXTENSIONS:
        if lower.endswith(ext): return "IMAGE_UPLOAD"
    for ext in VIDEO_EXTENSIONS:
        if lower.endswith(ext): return "VIDEO_UPLOAD"
    for ext in ZIP_EXTENSIONS:
        if lower.endswith(ext): return "ZIP_UPLOAD"
    return "FILE_UPLOAD"


def get_extension_category(ext: str) -> str:
    """Given an extension string, return which topic to search."""
    ext_dot = ext if ext.startswith('.') else f'.{ext}'
    ext_dot = ext_dot.lower()
    if ext_dot in IMAGE_EXTENSIONS: return "IMAGE_UPLOAD"
    if ext_dot in VIDEO_EXTENSIONS: return "VIDEO_UPLOAD"
    if ext_dot in ZIP_EXTENSIONS: return "ZIP_UPLOAD"
    return None  


def get_main_menu_keyboard():
    """Return the main menu inline keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload", callback_data="menu_upload"),
         InlineKeyboardButton("🔍 Search", callback_data="menu_search")],
        [InlineKeyboardButton("🤖 AI Chat", callback_data="menu_ai")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="menu_help"),
         InlineKeyboardButton("📊 Stats", callback_data="menu_stats")],
    ])


def _format_size(size_bytes):
    if not size_bytes: return "Unknown"
    if size_bytes < 1024: return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024: return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024: return f"{size_bytes / (1024 * 1024):.1f} MB"
    else: return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# ═══════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start and /menu commands cleanly."""
    await clean_ui(update, context)
    
    if not context.bot_data.get("db_loaded"):
        load_from_github(context.bot_data)
        context.bot_data["db_loaded"] = True
    
    storage_id = context.bot_data.get("STORAGE_CHAT_ID")
    topics = context.bot_data.get("topics", {})
    file_count = len(context.bot_data.get("file_index", []))
    
    status = "✅ Connected" if storage_id else "❌ Not Setup (Add me to 'MyStorage' group)"
    topics_status = "✅ Ready" if len(topics) == 4 else f"⚠️ {len(topics)}/4 Topics"
    
    text = (
        "🤖 <b>Super Main Bot</b>\n\n"
        f"📦 Storage: {status}\n"
        f"📂 Topics: {topics_status}\n"
        f"📁 Indexed Files: {file_count}\n\n"
        "Choose an option below:"
    )
    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard()
    )
    context.user_data["last_menu_id"] = msg.message_id


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cleanly display the help menu."""
    await clean_ui(update, context)
    help_text = (
        "ℹ️ <b>How to use this bot</b>\n\n"
        "<b>1. Setup Storage</b>\n"
        "Create a group named <code>MyStorage</code> and add me to it. I will automatically "
        "detect it, create the 4 required topics, and save the configuration to GitHub.\n\n"
        "<b>2. Upload Files</b>\n"
        "Click <b>Upload</b>, send as many files as you want, then type <code>/done</code>. "
        "I will automatically sort them into the correct group topics.\n\n"
        "<b>3. Search</b>\n"
        "Click <b>Search</b> to find your files by name or exact file extension.\n\n"
        "<b>4. AI Mode</b>\n"
        "Click <b>AI Chat</b> to speak with Gemini or send it images to analyze. "
        "Type <code>/done</code> to completely self-destruct the chat history and exit.\n\n"
        "<b>Clean UI</b>\n"
        "The bot automatically deletes old menus to keep your chat clean."
    )
    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
    )
    context.user_data["last_menu_id"] = msg.message_id


# ═══════════════════════════════════════════
# AUTO-DETECT STORAGE GROUP
# ═══════════════════════════════════════════

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-detect when bot is used in a group named 'MyStorage'."""
    if update.message and update.message.chat.type in ("group", "supergroup"):
        chat_id = update.message.chat_id
        chat_title = update.message.chat.title or ""
        
        if "mystorage" in chat_title.lower():
            if not context.bot_data.get("STORAGE_CHAT_ID"):
                context.bot_data["STORAGE_CHAT_ID"] = chat_id
                status_msg = await update.message.reply_text("🔄 MyStorage group detected! Creating routing topics...")
                
                # Create topics automatically
                icon_colors = {"IMAGE_UPLOAD": 16749490, "VIDEO_UPLOAD": 13338331, "ZIP_UPLOAD": 9367192, "FILE_UPLOAD": 7322096}
                
                for name in TOPIC_NAMES:
                    if name not in context.bot_data.get("topics", {}):
                        try:
                            topic: ForumTopic = await context.bot.create_forum_topic(
                                chat_id=chat_id, name=name, icon_color=icon_colors.get(name, 7322096)
                            )
                            context.bot_data.setdefault("topics", {})[name] = topic.message_thread_id
                        except Exception as e:
                            logger.error(f"Failed to create topic {name}: {e}")
                
                save_to_github(context.bot_data)
                await status_msg.edit_text("✅ Bot successfully linked to this group and saved to GitHub DB! Topics are ready.")


# ═══════════════════════════════════════════
# UPLOAD SYSTEM
# ═══════════════════════════════════════════

async def start_upload_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    storage_id = context.bot_data.get("STORAGE_CHAT_ID")
    topics = context.bot_data.get("topics", {})
    
    if not storage_id or len(topics) < 4:
        await query.edit_message_text(
            "❌ Storage not ready. Please create a group called <b>MyStorage</b> and add me to it first.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]])
        )
        return
    
    user_id = query.from_user.id
    context.bot_data.setdefault("upload_sessions", {})[user_id] = {"files": [], "active": True}
    
    text = (
        "📤 <b>Upload Session Started!</b>\n\n"
        "Send me your files now (Images, Videos, ZIPs, Docs). "
        "Files received: <b>0</b>\n\n"
        "When done, press <b>✅ Done</b> or type <code>/done</code>\n"
        "To cancel, press <b>❌ Cancel</b>"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Done - Upload All", callback_data="upload_done")],
        [InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")],
    ]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming files during an upload session."""
    user_id = update.message.from_user.id
    session = context.bot_data.get("upload_sessions", {}).get(user_id)
    if not session or not session.get("active"): return
    
    message = update.message
    file_info = None
    
    # Comprehensive File Parsing
    if message.document:
        file_info = {"file_id": message.document.file_id, "file_name": message.document.file_name or "unknown_file", "file_size": message.document.file_size, "mime_type": message.document.mime_type or "", "type": "document"}
    elif message.photo:
        photo = message.photo[-1]
        file_info = {"file_id": photo.file_id, "file_name": f"photo_{photo.file_unique_id}.jpg", "file_size": photo.file_size, "mime_type": "image/jpeg", "type": "photo"}
    elif message.video:
        file_info = {"file_id": message.video.file_id, "file_name": message.video.file_name or f"video_{message.video.file_unique_id}.mp4", "file_size": message.video.file_size, "mime_type": message.video.mime_type or "video/mp4", "type": "video"}
    elif message.animation:
        file_info = {"file_id": message.animation.file_id, "file_name": message.animation.file_name or f"animation_{message.animation.file_unique_id}.gif", "file_size": message.animation.file_size, "mime_type": message.animation.mime_type or "image/gif", "type": "animation"}
    elif message.audio:
        file_info = {"file_id": message.audio.file_id, "file_name": message.audio.file_name or f"audio_{message.audio.file_unique_id}.mp3", "file_size": message.audio.file_size, "mime_type": message.audio.mime_type or "audio/mpeg", "type": "audio"}
    elif message.voice:
        file_info = {"file_id": message.voice.file_id, "file_name": f"voice_{message.voice.file_unique_id}.ogg", "file_size": message.voice.file_size, "mime_type": message.voice.mime_type or "audio/ogg", "type": "voice"}
    elif message.video_note:
        file_info = {"file_id": message.video_note.file_id, "file_name": f"videonote_{message.video_note.file_unique_id}.mp4", "file_size": message.video_note.file_size, "mime_type": "video/mp4", "type": "video_note"}
    elif message.sticker:
        ext = ".webp" if not message.sticker.is_animated and not message.sticker.is_video else ".tgs" if message.sticker.is_animated else ".webm"
        file_info = {"file_id": message.sticker.file_id, "file_name": f"sticker_{message.sticker.file_unique_id}{ext}", "file_size": message.sticker.file_size, "mime_type": "image/webp", "type": "sticker"}
    
    if file_info:
        session["files"].append(file_info)
        category = get_file_category(file_info["file_name"])
        cat_emoji = {"IMAGE_UPLOAD": "📷", "VIDEO_UPLOAD": "🎬", "ZIP_UPLOAD": "📦", "FILE_UPLOAD": "📄"}.get(category, "📁")
        
        keyboard = [
            [InlineKeyboardButton("✅ Done - Upload All", callback_data="upload_done")],
            [InlineKeyboardButton("❌ Cancel", callback_data="upload_cancel")],
        ]
        await message.reply_text(
            f"{cat_emoji} File received: <b>{file_info['file_name']}</b>\n"
            f"Category: <b>{category}</b>\n"
            f"Total files in session: <b>{len(session['files'])}</b>\n\n"
            f"Send more files or press Done.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def _process_upload(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, is_callback: bool = False):
    """Process and forward all files to appropriate topics."""
    session = context.bot_data["upload_sessions"].get(user_id)
    if not session or not session["files"]:
        msg = "❌ No files to upload. Session cancelled."
        if is_callback: await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]))
        else: await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]))
        if user_id in context.bot_data["upload_sessions"]: del context.bot_data["upload_sessions"][user_id]
        return
    
    session["active"] = False
    storage_id = context.bot_data["STORAGE_CHAT_ID"]
    topics = context.bot_data["topics"]
    files = session["files"]
    
    status_text = f"⏳ Uploading {len(files)} file(s) to storage..."
    if is_callback: status_msg = await update.callback_query.edit_message_text(status_text)
    else: status_msg = await update.message.reply_text(status_text)
    
    results = {"success": 0, "fail": 0, "details": []}
    
    for f in files:
        category = get_file_category(f["file_name"])
        topic_id = topics.get(category)
        
        if not topic_id:
            results["fail"] += 1
            results["details"].append(f"❌ {f['file_name']} - Topic not found")
            continue
        
        try:
            caption = f"📁 {f['file_name']}"
            sent_msg = None
            
            if f["type"] == "photo": sent_msg = await context.bot.send_photo(chat_id=storage_id, message_thread_id=topic_id, photo=f["file_id"], caption=caption)
            elif f["type"] in ("video", "video_note"): sent_msg = await context.bot.send_video(chat_id=storage_id, message_thread_id=topic_id, video=f["file_id"], caption=caption)
            elif f["type"] == "animation": sent_msg = await context.bot.send_animation(chat_id=storage_id, message_thread_id=topic_id, animation=f["file_id"], caption=caption)
            elif f["type"] == "audio": sent_msg = await context.bot.send_audio(chat_id=storage_id, message_thread_id=topic_id, audio=f["file_id"], caption=caption)
            elif f["type"] == "voice": sent_msg = await context.bot.send_voice(chat_id=storage_id, message_thread_id=topic_id, voice=f["file_id"], caption=caption)
            else: sent_msg = await context.bot.send_document(chat_id=storage_id, message_thread_id=topic_id, document=f["file_id"], caption=caption)
            
            context.bot_data["file_index"].append({
                "file_name": f["file_name"], "file_id": f["file_id"], "category": category,
                "topic_id": topic_id, "message_id": sent_msg.message_id if sent_msg else None,
                "mime_type": f.get("mime_type", ""), "file_size": f.get("file_size", 0),
                "type": f["type"], "uploaded_by": user_id
            })
            
            results["success"] += 1
            cat_emoji = {"IMAGE_UPLOAD": "📷", "VIDEO_UPLOAD": "🎬", "ZIP_UPLOAD": "📦", "FILE_UPLOAD": "📄"}.get(category, "📁")
            results["details"].append(f"✅ {cat_emoji} {f['file_name']}")
        except Exception as e:
            results["fail"] += 1
            results["details"].append(f"❌ {f['file_name']} - Error")
            logger.error(f"Upload error: {e}")
    
    save_to_github(context.bot_data)
    del context.bot_data["upload_sessions"][user_id]
    
    detail_text = "\n".join(results["details"][:15])
    if len(results["details"]) > 15: detail_text += f"\n... and {len(results['details']) - 15} more"
    
    new_msg = await status_msg.edit_text(
        f"📤 <b>Upload Complete!</b>\n\n✅ Success: {results['success']} | ❌ Failed: {results['fail']}\n\n<b>Details:</b>\n{detail_text}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
    )
    context.user_data["last_menu_id"] = new_msg.message_id


async def upload_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id in context.bot_data.get("upload_sessions", {}):
        del context.bot_data["upload_sessions"][query.from_user.id]
    
    new_msg = await query.edit_message_text(
        "❌ Upload session cancelled.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
    )
    context.user_data["last_menu_id"] = new_msg.message_id


# ═══════════════════════════════════════════
# SEARCH SYSTEM
# ═══════════════════════════════════════════

async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📝 Search by Name", callback_data="search_byname")],
        [InlineKeyboardButton("📂 Search by File Type", callback_data="search_bytype")],
        [InlineKeyboardButton("📋 List All Files", callback_data="search_listall")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        f"🔍 <b>Search Files</b>\n\n📁 Total indexed files: <b>{len(context.bot_data.get('file_index', []))}</b>\n\nChoose search mode:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def search_byname_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.bot_data.setdefault("search_sessions", {})[query.from_user.id] = {"mode": "name"}
    await query.edit_message_text(
        "🔍 <b>Search by Name</b>\n\nType the name (or part of it) you want to search for.\nExample: <code>picture</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Search", callback_data="menu_search")]])
    )

async def search_bytype_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.bot_data.setdefault("search_sessions", {})[query.from_user.id] = {"mode": "type"}
    keyboard = [
        [InlineKeyboardButton("📷 Images", callback_data="searchtype_image"), InlineKeyboardButton("🎬 Videos", callback_data="searchtype_video")],
        [InlineKeyboardButton("📦 Archives", callback_data="searchtype_zip"), InlineKeyboardButton("📄 Documents", callback_data="searchtype_file")],
        [InlineKeyboardButton("✏️ Enter Extension", callback_data="searchtype_custom")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu_search")],
    ]
    await query.edit_message_text("🔍 <b>Search by File Type</b>\n\nChoose category or enter custom extension:", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def search_by_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    category = {"searchtype_image": "IMAGE_UPLOAD", "searchtype_video": "VIDEO_UPLOAD", "searchtype_zip": "ZIP_UPLOAD", "searchtype_file": "FILE_UPLOAD"}.get(query.data)
    if not category: return
    
    results = [f for f in context.bot_data.get("file_index", []) if f["category"] == category]
    await _send_search_results(update, context, results, f"Category: {category}")

async def searchtype_custom_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.bot_data.setdefault("search_sessions", {})[query.from_user.id] = {"mode": "extension"}
    await query.edit_message_text(
        "🔍 <b>Search by Extension</b>\n\nType the file extension.\nExample: <code>png</code> or <code>pdf</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="search_bytype")]])
    )

async def handle_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes text inputs for search terms."""
    user_id = update.message.from_user.id
    search_session = context.bot_data.get("search_sessions", {}).get(user_id)
    if not search_session: return
    
    # Delete the user's search text to keep chat clean
    try: await update.message.delete()
    except: pass
    
    query_text = update.message.text.strip().lower()
    file_index = context.bot_data.get("file_index", [])
    mode = search_session.get("mode")
    
    if mode == "name":
        results = [f for f in file_index if query_text in f["file_name"].lower()]
        title = f"Name: \"{query_text}\""
    elif mode == "extension":
        ext = query_text if query_text.startswith('.') else f'.{query_text}'
        target_category = get_extension_category(ext)
        if target_category: results = [f for f in file_index if f["category"] == target_category and f["file_name"].lower().endswith(ext)]
        else: results = [f for f in file_index if f["file_name"].lower().endswith(ext)]
        title = f"Extension: {ext}"
    else: return
    
    del context.bot_data["search_sessions"][user_id]
    await _send_search_results(update, context, results, title, is_message=True)

async def _send_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, results: list, title: str, is_message: bool = False):
    cat_emoji = {"IMAGE_UPLOAD": "📷", "VIDEO_UPLOAD": "🎬", "ZIP_UPLOAD": "📦", "FILE_UPLOAD": "📄"}
    
    if not results:
        text = f"🔍 <b>Search Results - {title}</b>\n\n❌ No files found."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Search Again", callback_data="menu_search")], [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
        if is_message: msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else: msg = await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        context.user_data["last_menu_id"] = msg.message_id
        return

    # Delete previous bot message if sending via Text Message to keep UI clean
    if is_message and "last_menu_id" in context.user_data:
        try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data["last_menu_id"])
        except: pass

    # Paginate/limit results display
    lines = [f"{i}. {cat_emoji.get(f['category'], '📁')} <code>{f['file_name']}</code> ({_format_size(f.get('file_size', 0))})" for i, f in enumerate(results[:30], 1)]
    text = f"🔍 <b>Search Results - {title}</b>\n\nFound: <b>{len(results)}</b> file(s)\n\n" + "\n".join(lines)
    if len(results) > 30: text += f"\n\n... and {len(results) - 30} more files"
    
    # Store for retrieval
    user_id = update.message.from_user.id if is_message else update.callback_query.from_user.id
    context.bot_data.setdefault("search_results", {})[user_id] = results
    
    keyboard = [[InlineKeyboardButton(f"📥 {f['file_name'][:30]}", callback_data=f"getfile_{i}")] for i, f in enumerate(results[:10])]
    keyboard.append([InlineKeyboardButton("🔙 Search Again", callback_data="menu_search")])
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
    
    if is_message: msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else: msg = await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["last_menu_id"] = msg.message_id

async def getfile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📥 Sending file...")
    
    user_id = query.from_user.id
    index = int(query.data.split("_")[1])
    results = context.bot_data.get("search_results", {}).get(user_id, [])
    
    if not results or index >= len(results):
        await query.answer("❌ File not found in cache", show_alert=True)
        return
        
    file_entry = results[index]
    caption = f"📁 {file_entry['file_name']}"
    f_type = file_entry.get("type", "document")
    
    try:
        if f_type == "photo": await context.bot.send_photo(chat_id=query.message.chat_id, photo=file_entry["file_id"], caption=caption)
        elif f_type in ("video", "video_note"): await context.bot.send_video(chat_id=query.message.chat_id, video=file_entry["file_id"], caption=caption)
        elif f_type == "animation": await context.bot.send_animation(chat_id=query.message.chat_id, animation=file_entry["file_id"], caption=caption)
        elif f_type == "audio": await context.bot.send_audio(chat_id=query.message.chat_id, audio=file_entry["file_id"], caption=caption)
        elif f_type == "voice": await context.bot.send_voice(chat_id=query.message.chat_id, voice=file_entry["file_id"], caption=caption)
        else: await context.bot.send_document(chat_id=query.message.chat_id, document=file_entry["file_id"], caption=caption)
    except Exception as e:
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Error sending file: {str(e)[:100]}")

async def search_listall_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_search_results(update, context, context.bot_data.get("file_index", []), "All Files")


# ═══════════════════════════════════════════
# STATS & MENU ROUTING
# ═══════════════════════════════════════════

async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    file_index = context.bot_data.get("file_index", [])
    cat_counts = {}
    total_size = 0
    for f in file_index:
        cat_counts[f.get("category", "unknown")] = cat_counts.get(f.get("category", "unknown"), 0) + 1
        total_size += f.get("file_size", 0) or 0
    
    lines = [f"{{'IMAGE_UPLOAD': '📷', 'VIDEO_UPLOAD': '🎬', 'ZIP_UPLOAD': '📦', 'FILE_UPLOAD': '📄'}.get(cat, '📁')} {cat}: <b>{cat_counts.get(cat, 0)}</b>" for cat in TOPIC_NAMES]
    
    new_msg = await query.edit_message_text(
        f"📊 <b>Storage Statistics</b>\n\n📁 Total Files: <b>{len(file_index)}</b>\n💾 Total Size: <b>{_format_size(total_size)}</b>\n\n" + "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
    )
    context.user_data["last_menu_id"] = new_msg.message_id


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    storage_id = context.bot_data.get("STORAGE_CHAT_ID")
    status = "✅ Connected" if storage_id else "❌ Not Setup (Add me to 'MyStorage' group)"
    
    text = (
        "🤖 <b>Super Main Bot</b>\n\n"
        f"📦 Storage: {status}\n"
        f"📁 Indexed Files: {len(context.bot_data.get('file_index', []))}\n\n"
        "Choose an option below:"
    )
    new_msg = await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu_keyboard())
    context.user_data["last_menu_id"] = new_msg.message_id


# ═══════════════════════════════════════════
# REGISTER HANDLERS (main1)
# ═══════════════════════════════════════════

def register_handlers(app):
    # Commands
    app.add_handler(CommandHandler(["start", "menu"], cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    
    # Auto-detect Group
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, handle_group_message))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(cmd_help, pattern="^menu_help$"))
    app.add_handler(CallbackQueryHandler(stats_callback, pattern="^menu_stats$"))
    
    # Upload Callbacks
    app.add_handler(CallbackQueryHandler(start_upload_session, pattern="^menu_upload$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: _process_upload(u, c, u.callback_query.from_user.id, True), pattern="^upload_done$"))
    app.add_handler(CallbackQueryHandler(upload_cancel_callback, pattern="^upload_cancel$"))
    
    # Search Callbacks
    app.add_handler(CallbackQueryHandler(start_search, pattern="^menu_search$"))
    app.add_handler(CallbackQueryHandler(search_byname_start, pattern="^search_byname$"))
    app.add_handler(CallbackQueryHandler(search_bytype_start, pattern="^search_bytype$"))
    app.add_handler(CallbackQueryHandler(search_listall_callback, pattern="^search_listall$"))
    app.add_handler(CallbackQueryHandler(search_by_category_callback, pattern="^searchtype_(image|video|zip|file)$"))
    app.add_handler(CallbackQueryHandler(searchtype_custom_callback, pattern="^searchtype_custom$"))
    app.add_handler(CallbackQueryHandler(getfile_callback, pattern=r"^getfile_\d+$"))
