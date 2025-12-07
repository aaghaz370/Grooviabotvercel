import os
import re
import json
import time
import asyncio
import logging
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from urllib.parse import quote, urlparse, parse_qs

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaAudio
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode, ChatAction

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
API_BASE = "https://jiosavan-sigma.vercel.app/api"
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x]

# User data storage (in-memory - for production use database)
user_data_store = {}
user_stats = {}
download_history = {}

# Quality settings
QUALITY_OPTIONS = {
    "high": {"quality": "320kbps", "desc": "🔥 High Quality (Slow)", "index": 4},
    "medium": {"quality": "160kbps", "desc": "⚡ Balanced (Medium)", "index": 3},
    "low": {"quality": "96kbps", "desc": "⚡️ Fast (Low)", "index": 2}
}

# Emoji constants
EMOJI = {
    "song": "🎵",
    "artist": "👤",
    "album": "💿",
    "playlist": "📚",
    "duration": "⏱",
    "language": "🌐",
    "year": "📅",
    "download": "⬇️",
    "similar": "🔄",
    "search": "🔍",
    "settings": "⚙️",
    "stats": "📊",
    "history": "📜",
    "fire": "🔥",
    "star": "⭐",
    "music": "🎶",
    "loading": "⏳"
}

# Helper Functions
def get_user_data(user_id: int) -> Dict:
    """Get or create user data"""
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "quality": "medium",
            "history": [],
            "downloads": 0,
            "searches": 0
        }
    return user_data_store[user_id]

def update_user_stats(user_id: int, action: str):
    """Update user statistics"""
    if user_id not in user_stats:
        user_stats[user_id] = {"downloads": 0, "searches": 0, "last_active": None}
    
    if action == "download":
        user_stats[user_id]["downloads"] += 1
    elif action == "search":
        user_stats[user_id]["searches"] += 1
    
    user_stats[user_id]["last_active"] = datetime.now().isoformat()

def format_duration(seconds: int) -> str:
    """Format duration from seconds to MM:SS"""
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins}:{secs:02d}"

def truncate_text(text: str, max_length: int = 30) -> str:
    """Truncate text with ellipsis"""
    return text[:max_length] + "..." if len(text) > max_length else text

def extract_jiosaavn_id(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract ID and type from JioSaavn URL"""
    try:
        parsed = urlparse(url)
        path = parsed.path
        
        if "/song/" in path:
            song_id = path.split("/")[-1]
            return song_id, "song"
        elif "/album/" in path:
            album_id = path.split("/")[-1]
            return album_id, "album"
        elif "/featured/" in path or "/playlist/" in path:
            playlist_id = path.split("/")[-1]
            return playlist_id, "playlist"
        elif "/artist/" in path:
            artist_id = path.split("/")[-1]
            return artist_id, "artist"
    except:
        pass
    return None, None

async def fetch_api(session: aiohttp.ClientSession, endpoint: str, params: Dict = None) -> Optional[Dict]:
    """Fetch data from JioSaavn API"""
    try:
        url = f"{API_BASE}/{endpoint}"
        async with session.get(url, params=params, timeout=30) as response:
            if response.status == 200:
                data = await response.json()
                return data if data.get("success") else None
    except Exception as e:
        logger.error(f"API fetch error: {e}")
    return None

async def search_songs(query: str, page: int = 0, limit: int = 10) -> Optional[Dict]:
    """Search for songs"""
    async with aiohttp.ClientSession() as session:
        return await fetch_api(session, "search/songs", {
            "query": query,
            "page": page,
            "limit": limit
        })

async def search_albums(query: str, page: int = 0, limit: int = 10) -> Optional[Dict]:
    """Search for albums"""
    async with aiohttp.ClientSession() as session:
        return await fetch_api(session, "search/albums", {
            "query": query,
            "page": page,
            "limit": limit
        })

async def search_playlists(query: str, page: int = 0, limit: int = 10) -> Optional[Dict]:
    """Search for playlists"""
    async with aiohttp.ClientSession() as session:
        return await fetch_api(session, "search/playlists", {
            "query": query,
            "page": page,
            "limit": limit
        })

async def search_artists(query: str, page: int = 0, limit: int = 10) -> Optional[Dict]:
    """Search for artists"""
    async with aiohttp.ClientSession() as session:
        return await fetch_api(session, "search/artists", {
            "query": query,
            "page": page,
            "limit": limit
        })

async def get_song_details(song_id: str) -> Optional[Dict]:
    """Get song details by ID"""
    async with aiohttp.ClientSession() as session:
        return await fetch_api(session, f"songs/{song_id}")

async def get_album_details(album_id: str) -> Optional[Dict]:
    """Get album details by ID"""
    async with aiohttp.ClientSession() as session:
        return await fetch_api(session, f"albums", {"id": album_id})

async def get_playlist_details(playlist_id: str, page: int = 0, limit: int = 50) -> Optional[Dict]:
    """Get playlist details by ID"""
    async with aiohttp.ClientSession() as session:
        return await fetch_api(session, "playlists", {
            "id": playlist_id,
            "page": page,
            "limit": limit
        })

async def get_artist_songs(artist_id: str, page: int = 0, limit: int = 10) -> Optional[Dict]:
    """Get artist songs"""
    async with aiohttp.ClientSession() as session:
        return await fetch_api(session, f"artists/{artist_id}/songs", {
            "page": page,
            "limit": limit
        })

async def get_artist_albums(artist_id: str, page: int = 0, limit: int = 10) -> Optional[Dict]:
    """Get artist albums"""
    async with aiohttp.ClientSession() as session:
        return await fetch_api(session, f"artists/{artist_id}/albums", {
            "page": page,
            "limit": limit
        })

async def get_song_suggestions(song_id: str, limit: int = 10) -> Optional[Dict]:
    """Get song suggestions"""
    async with aiohttp.ClientSession() as session:
        return await fetch_api(session, f"songs/{song_id}/suggestions", {"limit": limit})

def create_song_keyboard(song_id: str, show_similar: bool = True) -> InlineKeyboardMarkup:
    """Create inline keyboard for song"""
    buttons = [
        [InlineKeyboardButton(f"{EMOJI['download']} Download", callback_data=f"dl_{song_id}")],
    ]
    
    if show_similar:
        buttons.append([InlineKeyboardButton(f"{EMOJI['similar']} Similar Songs", callback_data=f"sim_{song_id}")])
    
    buttons.append([InlineKeyboardButton("🔙 Back to Search", callback_data="back_search")])
    
    return InlineKeyboardMarkup(buttons)

def create_pagination_keyboard(current_page: int, total_pages: int, prefix: str, query: str = "") -> InlineKeyboardMarkup:
    """Create pagination keyboard"""
    buttons = []
    
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"{prefix}_pg_{current_page-1}_{query}"))
    
    nav_buttons.append(InlineKeyboardButton(f"📄 {current_page + 1}/{total_pages}", callback_data="noop"))
    
    if current_page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"{prefix}_pg_{current_page+1}_{query}"))
    
    buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(buttons)

def create_list_keyboard(items: List[Dict], item_type: str, page: int, total_items: int, query: str = "") -> InlineKeyboardMarkup:
    """Create keyboard for list items with pagination"""
    buttons = []
    
    for i, item in enumerate(items):
        item_id = item.get("id")
        if item_type == "song":
            name = truncate_text(item.get("name", "Unknown"), 35)
            artist = truncate_text(item.get("artists", {}).get("primary", [{}])[0].get("name", "Unknown"), 20) if item.get("artists") else "Unknown"
            duration = format_duration(item.get("duration", 0))
            button_text = f"{EMOJI['song']} {name} • {artist} • {duration}"
            callback_data = f"song_{item_id}"
        elif item_type == "album":
            name = truncate_text(item.get("name", "Unknown"), 35)
            artist = truncate_text(item.get("artists", {}).get("primary", [{}])[0].get("name", "Unknown"), 20) if item.get("artists") else "Unknown"
            song_count = item.get("songCount", 0)
            button_text = f"{EMOJI['album']} {name} • {artist} • {song_count} songs"
            callback_data = f"album_{item_id}"
        elif item_type == "playlist":
            name = truncate_text(item.get("name", "Unknown"), 35)
            song_count = item.get("songCount", 0)
            button_text = f"{EMOJI['playlist']} {name} • {song_count} songs"
            callback_data = f"playlist_{item_id}"
        elif item_type == "artist":
            name = truncate_text(item.get("name", "Unknown"), 40)
            button_text = f"{EMOJI['artist']} {name}"
            callback_data = f"artist_{item_id}"
        else:
            continue
        
        buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Pagination
    limit = 10
    total_pages = (total_items + limit - 1) // limit
    
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"list_{item_type}_{page-1}_{query}"))
        
        nav_buttons.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="noop"))
        
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"list_{item_type}_{page+1}_{query}"))
        
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(buttons)

def create_album_playlist_keyboard(item_id: str, item_type: str, page: int = 0, total_songs: int = 0) -> InlineKeyboardMarkup:
    """Create keyboard for album/playlist details"""
    buttons = []
    
    # Download all button
    buttons.append([InlineKeyboardButton(f"{EMOJI['download']} Download All", callback_data=f"dlall_{item_type}_{item_id}")])
    
    # Pagination for songs
    if total_songs > 10:
        limit = 10
        total_pages = (total_songs + limit - 1) // limit
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"{item_type}detail_{item_id}_{page-1}"))
        
        nav_buttons.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="noop"))
        
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"{item_type}detail_{item_id}_{page+1}"))
        
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_search")])
    
    return InlineKeyboardMarkup(buttons)

def create_artist_keyboard(artist_id: str) -> InlineKeyboardMarkup:
    """Create keyboard for artist"""
    buttons = [
        [InlineKeyboardButton(f"{EMOJI['song']} View Songs", callback_data=f"artist_songs_{artist_id}_0")],
        [InlineKeyboardButton(f"{EMOJI['album']} View Albums", callback_data=f"artist_albums_{artist_id}_0")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_search")]
    ]
    return InlineKeyboardMarkup(buttons)

async def send_loading_animation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send loading animation"""
    loading_frames = [
        "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"
    ]
    
    message = await update.message.reply_text(
        f"{loading_frames[0]} Processing your request...",
        parse_mode=ParseMode.HTML
    )
    
    return message.message_id

async def update_loading_animation(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, text: str):
    """Update loading animation"""
    loading_frames = [
        "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"
    ]
    
    for frame in loading_frames:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"{frame} {text}",
                parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(0.1)
        except:
            break

async def delete_loading_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    """Delete loading message"""
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass

# Command Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    user_id = user.id
    
    # Initialize user data
    get_user_data(user_id)
    
    welcome_text = f"""
🎵 <b>Welcome to Groovia Music Bot!</b> 🎵

Hello {user.first_name}! 👋

I'm your advanced music companion powered by JioSaavn. I can help you:

{EMOJI['search']} <b>Search & Download</b>
• Songs in high quality
• Albums & Playlists
• Artist collections

{EMOJI['music']} <b>Smart Features</b>
• Direct URL support
• Similar song recommendations
• Download history
• Quality settings

{EMOJI['fire']} <b>Quick Start</b>
Just type any song name to search!

Or use the menu below to explore:
"""
    
    keyboard = [
        [
            InlineKeyboardButton(f"{EMOJI['search']} Search Songs", callback_data="search_songs"),
            InlineKeyboardButton(f"{EMOJI['album']} Albums", callback_data="search_albums")
        ],
        [
            InlineKeyboardButton(f"{EMOJI['playlist']} Playlists", callback_data="search_playlists"),
            InlineKeyboardButton(f"{EMOJI['artist']} Artists", callback_data="search_artists")
        ],
        [
            InlineKeyboardButton(f"{EMOJI['settings']} Settings", callback_data="settings"),
            InlineKeyboardButton(f"{EMOJI['history']} History", callback_data="history")
        ],
        [
            InlineKeyboardButton(f"{EMOJI['stats']} My Stats", callback_data="my_stats"),
            InlineKeyboardButton("ℹ️ Help", callback_data="help")
        ]
    ]
    
    if user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        await update.callback_query.message.edit_text(
            welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = """
📖 <b>How to Use Groovia Bot</b>

<b>🔍 Searching:</b>
1️⃣ Type any song name directly in chat
2️⃣ Or use menu buttons for specific searches
3️⃣ Browse through paginated results

<b>📥 Downloading:</b>
• Click on any song from results
• Tap "Download" button
• Song will be sent with album art

<b>🔗 Direct URLs:</b>
Paste any JioSaavn link:
• Song URLs → Direct download
• Album URLs → Full album view
• Playlist URLs → All songs
• Artist URLs → Artist profile

<b>⚙️ Settings:</b>
• Choose download quality
• High: 320kbps (slower)
• Medium: 160kbps (balanced)
• Low: 96kbps (faster)

<b>🎭 Features:</b>
• Similar song recommendations
• Download history tracking
• Personal statistics
• Album/Playlist batch downloads

<b>💡 Tips:</b>
• Use specific song names for better results
• Check similar songs for discoveries
• Download all from albums/playlists

Need more help? Contact @YourSupport
"""
    
    keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.callback_query.message.edit_text(help_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Settings command handler"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    current_quality = user_data.get("quality", "medium")
    
    settings_text = f"""
⚙️ <b>Settings</b>

<b>Current Download Quality:</b>
{QUALITY_OPTIONS[current_quality]['desc']}

<b>Choose your preferred quality:</b>

🔥 <b>High (320kbps)</b>
• Best audio quality
• Larger file size
• Slower download

⚡ <b>Medium (160kbps)</b>
• Balanced quality
• Moderate file size
• Good speed

⚡️ <b>Low (96kbps)</b>
• Faster downloads
• Smaller file size
• Lower quality

<i>Higher quality = Better sound but slower downloads</i>
"""
    
    keyboard = [
        [InlineKeyboardButton(
            f"{'✅ ' if current_quality == 'high' else ''}{QUALITY_OPTIONS['high']['desc']}",
            callback_data="quality_high"
        )],
        [InlineKeyboardButton(
            f"{'✅ ' if current_quality == 'medium' else ''}{QUALITY_OPTIONS['medium']['desc']}",
            callback_data="quality_medium"
        )],
        [InlineKeyboardButton(
            f"{'✅ ' if current_quality == 'low' else ''}{QUALITY_OPTIONS['low']['desc']}",
            callback_data="quality_low"
        )],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(settings_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.callback_query.message.edit_text(settings_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats command handler"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    stats = user_stats.get(user_id, {"downloads": 0, "searches": 0})
    
    stats_text = f"""
📊 <b>Your Statistics</b>

{EMOJI['download']} <b>Total Downloads:</b> {stats.get('downloads', 0)}
{EMOJI['search']} <b>Total Searches:</b> {stats.get('searches', 0)}
{EMOJI['music']} <b>Songs in History:</b> {len(user_data.get('history', []))}

{EMOJI['settings']} <b>Current Quality:</b> {QUALITY_OPTIONS[user_data.get('quality', 'medium')]['desc']}

Keep exploring music with Groovia! 🎵
"""
    
    keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.callback_query.message.edit_text(stats_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """History command handler"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    history = user_data.get("history", [])
    
    if not history:
        history_text = f"""
{EMOJI['history']} <b>Download History</b>

No downloads yet! Start searching for music to build your history.
"""
        keyboard = [[InlineKeyboardButton("🔍 Search Songs", callback_data="search_songs")]]
    else:
        history_text = f"{EMOJI['history']} <b>Recent Downloads</b>\n\n"
        
        for i, item in enumerate(history[-10:][::-1], 1):
            history_text += f"{i}. {item.get('name', 'Unknown')} - {item.get('artist', 'Unknown')}\n"
        
        keyboard = [
            [InlineKeyboardButton("🗑 Clear History", callback_data="clear_history")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(history_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.callback_query.message.edit_text(history_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel handler"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.callback_query.answer("⛔ Unauthorized access!", show_alert=True)
        return
    
    total_users = len(user_stats)
    total_downloads = sum(u.get("downloads", 0) for u in user_stats.values())
    total_searches = sum(u.get("searches", 0) for u in user_stats.values())
    
    admin_text = f"""
👑 <b>Admin Panel</b>

📊 <b>Bot Statistics:</b>
👥 Total Users: {total_users}
{EMOJI['download']} Total Downloads: {total_downloads}
{EMOJI['search']} Total Searches: {total_searches}

<b>Admin Actions:</b>
"""
    
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 Detailed Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.message.edit_text(admin_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

# Message Handlers
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages (search queries and URLs)"""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Check if it's a JioSaavn URL
    if "jiosaavn.com" in text or "saavn.com" in text:
        await handle_url(update, context, text)
        return
    
    # Check if it's lyrics request (more than 6 words)
    word_count = len(text.split())
    if word_count > 6:
        await update.message.reply_text(
            "🎤 Lyrics search is not yet implemented.\nPlease search for songs by their names!",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Regular song search
    await search_and_display(update, context, text, "song")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Handle JioSaavn URLs"""
    item_id, item_type = extract_jiosaavn_id(url)
    
    if not item_id or not item_type:
        await update.message.reply_text(
            "❌ Invalid JioSaavn URL. Please send a valid song, album, playlist, or artist URL.",
            parse_mode=ParseMode.HTML
        )
        return
    
    loading_msg = await update.message.reply_text(f"{EMOJI['loading']} Fetching details...")
    
    try:
        if item_type == "song":
            data = await get_song_details(item_id)
            if data and data.get("success"):
                await display_song_details(update, context, data["data"], edit_message=False)
        elif item_type == "album":
            data = await get_album_details(item_id)
            if data and data.get("success"):
                await display_album_details(update, context, data["data"], edit_message=False)
        elif item_type == "playlist":
            data = await get_playlist_details(item_id)
            if data and data.get("success"):
                await display_playlist_details(update, context, data["data"], edit_message=False)
        elif item_type == "artist":
            # For artist URLs, show artist menu
            keyboard = create_artist_keyboard(item_id)
            await update.message.reply_text(
                f"{EMOJI['artist']} <b>Artist Profile</b>\n\nChoose an option:",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
        
        await loading_msg.delete()
    except Exception as e:
        logger.error(f"Error handling URL: {e}")
        await loading_msg.edit_text("❌ Failed to fetch details. Please try again.")

async def search_and_display(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str, search_type: str, page: int = 0):
    """Search and display results"""
    user_id = update.effective_user.id
    update_user_stats(user_id, "search")
    
    # Store search context
    context.user_data["last_search"] = {"query": query, "type": search_type, "page": page}
    
    loading_msg = None
    if update.message:
        loading_msg = await update.message.reply_text(f"{EMOJI['loading']} Searching...")
    
    try:
        if search_type == "song":
            data = await search_songs(query, page, 10)
        elif search_type == "album":
            data = await search_albums(query, page, 10)
        elif search_type == "playlist":
            data = await search_playlists(query, page, 10)
        elif search_type == "artist":
            data = await search_artists(query, page, 10)
        else:
            return
        
        if loading_msg:
            await loading_msg.delete()
        
        if not data or not data.get("success"):
            error_text = f"❌ No {search_type}s found for '{query}'.\n\nTry different keywords or check spelling."
            keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
            
            if update.message:
                await update.message.reply_text(error_text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await update.callback_query.message.edit_text(error_text, reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        results = data.get("data", {}).get("results", [])
        total = data.get("data", {}).get("total", 0)
        
        if not results:
            error_text = f"❌ No {search_type}s found for '{query}'."
            keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
            
            if update.message:
                await update.message.reply_text(error_text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await update.callback_query.message.edit_text(error_text, reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Display results
        result_text = f"{EMOJI['search']} <b>Search Results for:</b> {query}\n"
        result_text += f"📊 Found {total} {search_type}(s)\n\n"
        result_text += "Select an item from the list below:"
        
        keyboard = create_list_keyboard(results, search_type, page, total, query)
        
        if update.message:
            await update.message.reply_text(result_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        else:
            await update.callback_query.message.edit_text(result_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    
    except Exception as e:
        logger.error(f"Search error: {e}")
        if loading_msg:
            await loading_msg.edit_text("❌ Search failed. Please try again.")

async def display_song_details(update: Update, context: ContextTypes.DEFAULT_TYPE, song_data: Dict, edit_message: bool = True):
    """Display song details"""
    try:
        song_id = song_data.get("id")
        name = song_data.get("name", "Unknown")
        artists = song_data.get("artists", {})
        primary_artists = artists.get("primary", [])
        artist_names = ", ".join([a.get("name", "Unknown") for a in primary_artists]) if primary_artists else "Unknown"
        
        album_name = song_data.get("album", {}).get("name", "Unknown")
        duration = format_duration(song_data.get("duration", 0))
        language = song_data.get("language", "Unknown").title()
        year = song_data.get("year", "Unknown")
        play_count = song_data.get("playCount", 0)
        
        # Get best quality image
        images = song_data.get("image", [])
        image_url = images[-1].get("url") if images else None
        
        caption = f"""
{EMOJI['song']} <b>{name}</b>

{EMOJI['artist']} <b>Artist:</b> {artist_names}
{EMOJI['album']} <b>Album:</b> {album_name}
{EMOJI['duration']} <b>Duration:</b> {duration}
{EMOJI['language']} <b>Language:</b> {language}
{EMOJI['year']} <b>Year:</b> {year}
{EMOJI['fire']} <b>Plays:</b> {play_count:,}

Tap below to download or find similar songs!
"""
        
        keyboard = create_song_keyboard(song_id)
        
        if image_url:
            if edit_message and update.callback_query:
                # Delete old message and send new one with photo
                await update.callback_query.message.delete()
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=image_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
            else:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=image_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
        else:
            if edit_message and update.callback_query:
                await update.callback_query.message.edit_text(caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            else:
                await update.message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    
    except Exception as e:
        logger.error(f"Error displaying song: {e}")

async def display_album_details(update: Update, context: ContextTypes.DEFAULT_TYPE, album_data: Dict, page: int = 0, edit_message: bool = True):
    """Display album details"""
    try:
        album_id = album_data.get("id")
        name = album_data.get("name", "Unknown")
        artists = album_data.get("artists", {})
        primary_artists = artists.get("primary", [])
        artist_names = ", ".join([a.get("name", "Unknown") for a in primary_artists]) if primary_artists else "Unknown"
        
        year = album_data.get("year", "Unknown")
        song_count = album_data.get("songCount", 0)
        songs = album_data.get("songs", [])
        
        # Get image
        images = album_data.get("image", [])
        image_url = images[-1].get("url") if images else None
        
        # Pagination for songs
        start_idx = page * 10
        end_idx = start_idx + 10
        displayed_songs = songs[start_idx:end_idx]
        
        caption = f"""
{EMOJI['album']} <b>{name}</b>

{EMOJI['artist']} <b>Artist:</b> {artist_names}
{EMOJI['year']} <b>Year:</b> {year}
{EMOJI['music']} <b>Total Songs:</b> {song_count}

<b>📝 Track List (Page {page + 1}):</b>
"""
        
        for i, song in enumerate(displayed_songs, start_idx + 1):
            song_name = truncate_text(song.get("name", "Unknown"), 30)
            song_duration = format_duration(song.get("duration", 0))
            caption += f"\n{i}. {song_name} • {song_duration}"
        
        caption += "\n\n💡 Tap a song number below or download all!"
        
        # Create song selection buttons
        keyboard = []
        song_row = []
        for i, song in enumerate(displayed_songs, start_idx + 1):
            song_row.append(InlineKeyboardButton(str(i), callback_data=f"song_{song.get('id')}"))
            if len(song_row) == 5:
                keyboard.append(song_row)
                song_row = []
        if song_row:
            keyboard.append(song_row)
        
        # Add control buttons
        control_keyboard = create_album_playlist_keyboard(album_id, "album", page, song_count)
        keyboard.extend(control_keyboard.inline_keyboard)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if image_url:
            if edit_message and update.callback_query:
                await update.callback_query.message.delete()
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=image_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            else:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=image_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
        else:
            if edit_message and update.callback_query:
                await update.callback_query.message.edit_text(caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            else:
                await update.message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    
    except Exception as e:
        logger.error(f"Error displaying album: {e}")

async def display_playlist_details(update: Update, context: ContextTypes.DEFAULT_TYPE, playlist_data: Dict, page: int = 0, edit_message: bool = True):
    """Display playlist details"""
    try:
        playlist_id = playlist_data.get("id")
        name = playlist_data.get("name", "Unknown")
        song_count = playlist_data.get("songCount", 0)
        songs = playlist_data.get("songs", [])
        
        # Get image
        images = playlist_data.get("image", [])
        image_url = images[-1].get("url") if images else None
        
        # Pagination for songs
        start_idx = page * 10
        end_idx = start_idx + 10
        displayed_songs = songs[start_idx:end_idx]
        
        caption = f"""
{EMOJI['playlist']} <b>{name}</b>

{EMOJI['music']} <b>Total Songs:</b> {song_count}

<b>📝 Track List (Page {page + 1}):</b>
"""
        
        for i, song in enumerate(displayed_songs, start_idx + 1):
            song_name = truncate_text(song.get("name", "Unknown"), 30)
            song_artists = song.get("artists", {}).get("primary", [])
            artist_name = song_artists[0].get("name", "Unknown") if song_artists else "Unknown"
            song_duration = format_duration(song.get("duration", 0))
            caption += f"\n{i}. {song_name} • {artist_name} • {song_duration}"
        
        caption += "\n\n💡 Tap a song number below or download all!"
        
        # Create song selection buttons
        keyboard = []
        song_row = []
        for i, song in enumerate(displayed_songs, start_idx + 1):
            song_row.append(InlineKeyboardButton(str(i), callback_data=f"song_{song.get('id')}"))
            if len(song_row) == 5:
                keyboard.append(song_row)
                song_row = []
        if song_row:
            keyboard.append(song_row)
        
        # Add control buttons
        control_keyboard = create_album_playlist_keyboard(playlist_id, "playlist", page, song_count)
        keyboard.extend(control_keyboard.inline_keyboard)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if image_url:
            if edit_message and update.callback_query:
                await update.callback_query.message.delete()
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=image_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            else:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=image_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
        else:
            if edit_message and update.callback_query:
                await update.callback_query.message.edit_text(caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            else:
                await update.message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    
    except Exception as e:
        logger.error(f"Error displaying playlist: {e}")

async def download_song(update: Update, context: ContextTypes.DEFAULT_TYPE, song_id: str):
    """Download and send song"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    quality = user_data.get("quality", "medium")
    
    try:
        # Show loading
        await update.callback_query.answer(f"{EMOJI['loading']} Downloading...")
        
        loading_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        loading_msg = await update.callback_query.message.reply_text(
            f"{loading_frames[0]} Preparing your download..."
        )
        
        # Fetch song details
        data = await get_song_details(song_id)
        
        if not data or not data.get("success"):
            await loading_msg.edit_text("❌ Failed to fetch song details.")
            return
        
        song_data = data["data"]
        name = song_data.get("name", "Unknown")
        artists = song_data.get("artists", {})
        primary_artists = artists.get("primary", [])
        artist_names = ", ".join([a.get("name", "Unknown") for a in primary_artists]) if primary_artists else "Unknown"
        
        # Get download URL
        download_urls = song_data.get("downloadUrl", [])
        quality_index = QUALITY_OPTIONS[quality]["index"]
        
        download_url = None
        if quality_index < len(download_urls):
            download_url = download_urls[quality_index].get("url")
        elif download_urls:
            download_url = download_urls[-1].get("url")
        
        if not download_url:
            await loading_msg.edit_text("❌ Download URL not available.")
            return
        
        # Animate loading
        for i in range(3):
            for frame in loading_frames:
                try:
                    await loading_msg.edit_text(f"{frame} Downloading {name}...")
                    await asyncio.sleep(0.15)
                except:
                    break
        
        # Send typing action
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_AUDIO)
        
        # Get thumbnail
        images = song_data.get("image", [])
        thumbnail_url = images[-1].get("url") if images else None
        
        # Download audio file
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as resp:
                if resp.status == 200:
                    audio_data = await resp.read()
                    
                    # Download thumbnail if available
                    thumb_data = None
                    if thumbnail_url:
                        async with session.get(thumbnail_url) as thumb_resp:
                            if thumb_resp.status == 200:
                                thumb_data = await thumb_resp.read()
                    
                    # Send audio
                    caption = f"{EMOJI['song']} <b>{name}</b>\n{EMOJI['artist']} {artist_names}\n\nDownloaded via @Grooviabot"
                    
                    await context.bot.send_audio(
                        chat_id=update.effective_chat.id,
                        audio=audio_data,
                        thumbnail=thumb_data if thumb_data else None,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        title=name,
                        performer=artist_names,
                        duration=song_data.get("duration", 0)
                    )
                    
                    # Update stats and history
                    update_user_stats(user_id, "download")
                    user_data["downloads"] = user_data.get("downloads", 0) + 1
                    user_data["history"].append({
                        "name": name,
                        "artist": artist_names,
                        "id": song_id
                    })
                    
                    # Keep only last 50 items in history
                    if len(user_data["history"]) > 50:
                        user_data["history"] = user_data["history"][-50:]
                    
                    await loading_msg.delete()
                else:
                    await loading_msg.edit_text("❌ Failed to download song.")
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        try:
            await loading_msg.edit_text("❌ Download failed. Please try again.")
        except:
            await update.callback_query.message.reply_text("❌ Download failed. Please try again.")

async def download_all_songs(update: Update, context: ContextTypes.DEFAULT_TYPE, item_id: str, item_type: str):
    """Download all songs from album/playlist"""
    user_id = update.effective_user.id
    
    try:
        await update.callback_query.answer("⏳ Starting batch download...")
        
        # Fetch all songs
        if item_type == "album":
            data = await get_album_details(item_id)
        else:  # playlist
            data = await get_playlist_details(item_id, page=0, limit=100)
        
        if not data or not data.get("success"):
            await update.callback_query.message.reply_text("❌ Failed to fetch songs.")
            return
        
        songs = data["data"].get("songs", [])
        
        if not songs:
            await update.callback_query.message.reply_text("❌ No songs found.")
            return
        
        total_songs = len(songs)
        status_msg = await update.callback_query.message.reply_text(
            f"📥 Downloading {total_songs} songs...\n⏳ Progress: 0/{total_songs}"
        )
        
        user_data = get_user_data(user_id)
        quality = user_data.get("quality", "medium")
        quality_index = QUALITY_OPTIONS[quality]["index"]
        
        # Download and send each song
        for idx, song in enumerate(songs, 1):
            try:
                song_id = song.get("id")
                name = song.get("name", "Unknown")
                artists = song.get("artists", {})
                primary_artists = artists.get("primary", [])
                artist_names = ", ".join([a.get("name", "Unknown") for a in primary_artists]) if primary_artists else "Unknown"
                
                # Update progress
                await status_msg.edit_text(
                    f"📥 Downloading {total_songs} songs...\n⏳ Progress: {idx}/{total_songs}\n🎵 {name}"
                )
                
                # Get song details if not available
                if not song.get("downloadUrl"):
                    song_data_response = await get_song_details(song_id)
                    if song_data_response and song_data_response.get("success"):
                        song = song_data_response["data"]
                
                download_urls = song.get("downloadUrl", [])
                
                download_url = None
                if quality_index < len(download_urls):
                    download_url = download_urls[quality_index].get("url")
                elif download_urls:
                    download_url = download_urls[-1].get("url")
                
                if not download_url:
                    continue
                
                # Download and send
                async with aiohttp.ClientSession() as session:
                    async with session.get(download_url, timeout=60) as resp:
                        if resp.status == 200:
                            audio_data = await resp.read()
                            
                            # Get thumbnail
                            images = song.get("image", [])
                            thumbnail_url = images[-1].get("url") if images else None
                            
                            thumb_data = None
                            if thumbnail_url:
                                async with session.get(thumbnail_url) as thumb_resp:
                                    if thumb_resp.status == 200:
                                        thumb_data = await thumb_resp.read()
                            
                            caption = f"{EMOJI['song']} <b>{name}</b>\n{EMOJI['artist']} {artist_names}\n\nDownloaded via @Grooviabot"
                            
                            await context.bot.send_audio(
                                chat_id=update.effective_chat.id,
                                audio=audio_data,
                                thumbnail=thumb_data if thumb_data else None,
                                caption=caption,
                                parse_mode=ParseMode.HTML,
                                title=name,
                                performer=artist_names,
                                duration=song.get("duration", 0)
                            )
                            
                            # Update stats
                            update_user_stats(user_id, "download")
                            
                            # Small delay to avoid flooding
                            await asyncio.sleep(1)
            
            except Exception as e:
                logger.error(f"Error downloading song {idx}: {e}")
                continue
        
        await status_msg.edit_text(
            f"✅ Download complete!\n📥 Successfully sent {total_songs} songs."
        )
    
    except Exception as e:
        logger.error(f"Batch download error: {e}")
        await update.callback_query.message.reply_text("❌ Batch download failed.")

# Callback Query Handler
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    try:
        # Main menu
        if data == "main_menu":
            await start_command(update, context)
        
        # Help
        elif data == "help":
            await help_command(update, context)
        
        # Settings
        elif data == "settings":
            await settings_command(update, context)
        
        # Quality settings
        elif data.startswith("quality_"):
            quality_choice = data.split("_")[1]
            user_id = update.effective_user.id
            user_data = get_user_data(user_id)
            user_data["quality"] = quality_choice
            
            await query.answer(f"✅ Quality set to {QUALITY_OPTIONS[quality_choice]['desc']}", show_alert=True)
            await settings_command(update, context)
        
        # Stats
        elif data == "my_stats":
            await stats_command(update, context)
        
        # History
        elif data == "history":
            await history_command(update, context)
        
        # Clear history
        elif data == "clear_history":
            user_id = update.effective_user.id
            user_data = get_user_data(user_id)
            user_data["history"] = []
            await query.answer("✅ History cleared!", show_alert=True)
            await history_command(update, context)
        
        # Search menus
        elif data == "search_songs":
            await query.message.edit_text(
                f"{EMOJI['search']} <b>Search Songs</b>\n\nType the name of the song you want to search:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
            )
            context.user_data["search_mode"] = "song"
        
        elif data == "search_albums":
            await query.message.edit_text(
                f"{EMOJI['album']} <b>Search Albums</b>\n\nType the name of the album you want to search:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
            )
            context.user_data["search_mode"] = "album"
        
        elif data == "search_playlists":
            await query.message.edit_text(
                f"{EMOJI['playlist']} <b>Search Playlists</b>\n\nType the name of the playlist you want to search:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
            )
            context.user_data["search_mode"] = "playlist"
        
        elif data == "search_artists":
            await query.message.edit_text(
                f"{EMOJI['artist']} <b>Search Artists</b>\n\nType the name of the artist you want to search:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
            )
            context.user_data["search_mode"] = "artist"
        
        # Song details
        elif data.startswith("song_"):
            song_id = data.split("_", 1)[1]
            song_data_response = await get_song_details(song_id)
            if song_data_response and song_data_response.get("success"):
                await display_song_details(update, context, song_data_response["data"])
        
        # Album details
        elif data.startswith("album_"):
            album_id = data.split("_", 1)[1]
            album_data_response = await get_album_details(album_id)
            if album_data_response and album_data_response.get("success"):
                await display_album_details(update, context, album_data_response["data"])
        
        # Playlist details
        elif data.startswith("playlist_"):
            playlist_id = data.split("_", 1)[1]
            playlist_data_response = await get_playlist_details(playlist_id)
            if playlist_data_response and playlist_data_response.get("success"):
                await display_playlist_details(update, context, playlist_data_response["data"])
        
        # Artist menu
        elif data.startswith("artist_") and not data.startswith("artist_songs") and not data.startswith("artist_albums"):
            artist_id = data.split("_", 1)[1]
            keyboard = create_artist_keyboard(artist_id)
            await query.message.edit_text(
                f"{EMOJI['artist']} <b>Artist Profile</b>\n\nChoose an option:",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
        
        # Artist songs
        elif data.startswith("artist_songs_"):
            parts = data.split("_")
            artist_id = parts[2]
            page = int(parts[3]) if len(parts) > 3 else 0
            
            songs_data = await get_artist_songs(artist_id, page, 10)
            if songs_data and songs_data.get("success"):
                results = songs_data.get("data", {}).get("songs", [])
                total = songs_data.get("data", {}).get("total", 0)
                
                result_text = f"{EMOJI['artist']} <b>Artist Songs</b>\n\nSelect a song:"
                keyboard = create_list_keyboard(results, "song", page, total, artist_id)
                await query.message.edit_text(result_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        
        # Artist albums
        elif data.startswith("artist_albums_"):
            parts = data.split("_")
            artist_id = parts[2]
            page = int(parts[3]) if len(parts) > 3 else 0
            
            albums_data = await get_artist_albums(artist_id, page, 10)
            if albums_data and albums_data.get("success"):
                results = albums_data.get("data", {}).get("albums", [])
                total = songs_data.get("data", {}).get("total", 0)
                
                result_text = f"{EMOJI['artist']} <b>Artist Albums</b>\n\nSelect an album:"
                keyboard = create_list_keyboard(results, "album", page, total, artist_id)
                await query.message.edit_text(result_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        
        # Download song
        elif data.startswith("dl_"):
            song_id = data.split("_", 1)[1]
            await download_song(update, context, song_id)
        
        # Download all
        elif data.startswith("dlall_"):
            parts = data.split("_")
            item_type = parts[1]
            item_id = parts[2]
            await download_all_songs(update, context, item_id, item_type)
        
        # Similar songs
        elif data.startswith("sim_"):
            song_id = data.split("_", 1)[1]
            suggestions_data = await get_song_suggestions(song_id, 10)
            
            if suggestions_data and suggestions_data.get("success"):
                results = suggestions_data.get("data", [])
                result_text = f"{EMOJI['similar']} <b>Similar Songs</b>\n\nSelect a song:"
                keyboard = create_list_keyboard(results, "song", 0, len(results))
                await query.message.edit_text(result_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        
        # List pagination
        elif data.startswith("list_"):
            parts = data.split("_")
            item_type = parts[1]
            page = int(parts[2])
            query_text = "_".join(parts[3:]) if len(parts) > 3 else ""
            
            last_search = context.user_data.get("last_search", {})
            if last_search and last_search.get("query"):
                await search_and_display(update, context, last_search["query"], item_type, page)
        
        # Album/Playlist detail pagination
        elif data.startswith("albumdetail_") or data.startswith("playlistdetail_"):
            parts = data.split("_")
            item_type = "album" if data.startswith("albumdetail") else "playlist"
            item_id = parts[1]
            page = int(parts[2]) if len(parts) > 2 else 0
            
            if item_type == "album":
                album_data = await get_album_details(item_id)
                if album_data and album_data.get("success"):
                    await display_album_details(update, context, album_data["data"], page)
            else:
                playlist_data = await get_playlist_details(item_id, page=0, limit=100)
                if playlist_data and playlist_data.get("success"):
                    await display_playlist_details(update, context, playlist_data["data"], page)
        
        # Admin panel
        elif data == "admin_panel":
            await admin_panel(update, context)
        
        # Admin broadcast (placeholder)
        elif data == "admin_broadcast":
            await query.answer("📢 Broadcast feature - Send a message to broadcast", show_alert=True)
            context.user_data["admin_mode"] = "broadcast"
        
        # Admin stats
        elif data == "admin_stats":
            user_id = update.effective_user.id
            if user_id not in ADMIN_IDS:
                await query.answer("⛔ Unauthorized!", show_alert=True)
                return
            
            total_users = len(user_stats)
            total_downloads = sum(u.get("downloads", 0) for u in user_stats.values())
            total_searches = sum(u.get("searches", 0) for u in user_stats.values())
            
            # Top users by downloads
            top_downloaders = sorted(
                [(uid, stats.get("downloads", 0)) for uid, stats in user_stats.items()],
                key=lambda x: x[1],
                reverse=True
            )[:5]
            
            stats_text = f"""
📊 <b>Detailed Bot Statistics</b>

👥 <b>Total Users:</b> {total_users}
{EMOJI['download']} <b>Total Downloads:</b> {total_downloads}
{EMOJI['search']} <b>Total Searches:</b> {total_searches}

<b>🏆 Top Downloaders:</b>
"""
            
            for idx, (uid, count) in enumerate(top_downloaders, 1):
                stats_text += f"\n{idx}. User {uid}: {count} downloads"
            
            keyboard = [[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]
            await query.message.edit_text(stats_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Back to search
        elif data == "back_search":
            last_search = context.user_data.get("last_search")
            if last_search:
                await search_and_display(
                    update,
                    context,
                    last_search["query"],
                    last_search["type"],
                    last_search.get("page", 0)
                )
            else:
                await start_command(update, context)
        
        # No operation
        elif data == "noop":
            await query.answer()
    
    except Exception as e:
        logger.error(f"Callback query error: {e}")
        await query.answer("❌ An error occurred. Please try again.", show_alert=True)

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin broadcast message handler"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        return
    
    if context.user_data.get("admin_mode") != "broadcast":
        return
    
    message_text = update.message.text
    
    if not message_text:
        await update.message.reply_text("❌ Please send a text message to broadcast.")
        return
    
    # Confirm broadcast
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm Broadcast", callback_data="broadcast_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")
        ]
    ]
    
    context.user_data["broadcast_message"] = message_text
    
    await update.message.reply_text(
        f"📢 <b>Confirm Broadcast</b>\n\n<b>Message:</b>\n{message_text}\n\n<b>Users:</b> {len(user_stats)}\n\nConfirm?",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and execute broadcast"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("⛔ Unauthorized!", show_alert=True)
        return
    
    await query.answer()
    
    broadcast_msg = context.user_data.get("broadcast_message")
    if not broadcast_msg:
        await query.message.edit_text("❌ No broadcast message found.")
        return
    
    status_msg = await query.message.edit_text(
        f"📢 <b>Broadcasting...</b>\n\n⏳ Progress: 0/{len(user_stats)}",
        parse_mode=ParseMode.HTML
    )
    
    success_count = 0
    failed_count = 0
    
    for idx, uid in enumerate(user_stats.keys(), 1):
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 <b>Announcement</b>\n\n{broadcast_msg}",
                parse_mode=ParseMode.HTML
            )
            success_count += 1
            
            if idx % 10 == 0:
                await status_msg.edit_text(
                    f"📢 <b>Broadcasting...</b>\n\n⏳ Progress: {idx}/{len(user_stats)}\n✅ Success: {success_count}\n❌ Failed: {failed_count}",
                    parse_mode=ParseMode.HTML
                )
            
            await asyncio.sleep(0.05)  # Rate limiting
        except Exception as e:
            logger.error(f"Broadcast error for user {uid}: {e}")
            failed_count += 1
    
    await status_msg.edit_text(
        f"✅ <b>Broadcast Complete!</b>\n\n👥 Total Users: {len(user_stats)}\n✅ Success: {success_count}\n❌ Failed: {failed_count}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]])
    )
    
    context.user_data["admin_mode"] = None
    context.user_data["broadcast_message"] = None

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred while processing your request. Please try again later."
            )
    except:
        pass

# Health check endpoint (for Render)
async def health_check(request):
    """Simple health check endpoint"""
    return {"status": "ok", "uptime": time.time()}

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("history", history_command))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Callback query handler
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    logger.info("🎵 Groovia Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
