#!/usr/bin/env python3
"""
Music Planner Telegram Bot v3.0
Full-featured AI music generation via Telegram

All generate.sh features accessible via bot commands.
"""

import os
import sys
import asyncio
import logging
import subprocess
import re
from pathlib import Path
from datetime import datetime

# Telegram bot library
try:
    from telegram import Update, Bot
    from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
except ImportError:
    print("Installing python-telegram-bot...")
    subprocess.run([sys.executable, "-m", "pip", "install", "python-telegram-bot", "-q"])
    from telegram import Update, Bot
    from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Configuration
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
SCRIPT_DIR = Path(__file__).parent
GENERATE_SCRIPT = SCRIPT_DIR / "generate.sh"

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Track active generations to prevent spam
active_generations = {}


def run_generate(args: list, timeout: int = 600):
    """Run generate.sh with arguments and return output + audio file path"""
    cmd = ["bash", str(GENERATE_SCRIPT)] + args
    logger.info(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(SCRIPT_DIR)
        )
        output = result.stdout + result.stderr
        
        # Extract audio file path(s)
        audio_files = []
        for line in output.split('\n'):
            if 'AUDIO_FILE=' in line:
                audio_file = line.split('AUDIO_FILE=')[1].strip()
                if audio_file and os.path.exists(audio_file):
                    audio_files.append(audio_file)
        
        # Clean output for Telegram (remove ANSI codes)
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', output)
        # Truncate if too long
        if len(clean_output) > 3500:
            clean_output = clean_output[:1500] + "\n...\n" + clean_output[-1500:]
        
        return clean_output, audio_files[0] if audio_files else None, audio_files
        
    except subprocess.TimeoutExpired:
        return "❌ Generation timed out (10 min limit)", None, []
    except Exception as e:
        return f"❌ Error: {str(e)}", None, []


def parse_args(text: str) -> list:
    """Parse command text into arguments, respecting quotes"""
    args = []
    current = ""
    in_quotes = False
    quote_char = None
    
    for char in text:
        if char in '"\'':
            if not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char:
                in_quotes = False
                if current:
                    args.append(current)
                    current = ""
                quote_char = None
            else:
                current += char
        elif char == ' ' and not in_quotes:
            if current:
                args.append(current)
                current = ""
        else:
            current += char
    
    if current:
        args.append(current)
    
    return args


def clean_for_telegram(text: str, max_len: int = 4000) -> str:
    """Clean output for Telegram display"""
    # Remove ANSI codes
    clean = re.sub(r'\x1b\[[0-9;]*m', '', text)
    # Truncate if needed
    if len(clean) > max_len:
        clean = clean[:max_len-100] + "\n...(truncated)"
    return clean


async def send_audio_files(update: Update, audio_files: list, title: str, performer: str):
    """Send audio files to chat"""
    for i, audio_file in enumerate(audio_files):
        if audio_file and os.path.exists(audio_file):
            suffix = f" (Take {i+1})" if len(audio_files) > 1 else ""
            with open(audio_file, 'rb') as f:
                await update.message.reply_audio(
                    audio=f,
                    title=f"{title}{suffix}",
                    performer=performer,
                    caption=f"🎵 {performer} - {title}{suffix}"
                )


# ═══════════════════════════════════════════════════════════════
# BASIC COMMANDS
# ═══════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    welcome = """🎵 *Music Planner Bot v3.0*

Generate AI music with ACE-Step right from Telegram!

*Quick Start:*
`/generate nova "a song about city lights"`

*Popular Commands:*
/help — Full command list
/artists — List AI artists
/generate — Create a song
/fusion — Mix two genres
/like — Sound-alike mode

*Create Content:*
/newartist — Create AI artist
/newgenre — Create genre guide

*Management:*
/catalog — View songs
/stats — Statistics
/queue — Batch generation

Let's make some music! 🎸"""
    
    await update.message.reply_text(welcome, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive help"""
    help_text = """🎵 *Music Planner Bot — Full Command List*

*━━━ GENERATION ━━━*
`/generate <artist> <concept>` — Basic generation
`/g` — Shortcut for /generate
`/collab <a1> <a2> <concept>` — Two artists collaborate
`/battle <a1> <a2> <concept>` — Same concept, two versions
`/album <artist> <theme>` — Generate 4-5 song EP
`/vibe <mood> <concept>` — Auto-pick artist by mood
`/fusion <g1> <g2> <concept>` — Fuse two genres
`/like <artist> <concept>` — Sound-alike mode
`/remix <song_id> <artist>` — Remix with new style
`/reroll <song_id>` — Regenerate with new seed
`/lyrics <your lyrics>` — Match lyrics to artist

*━━━ OPTIONS ━━━*
Add after concept:
`--quality draft|normal|high|ultra`
`--takes N` — Generate N versions
`--master` — Apply mastering

*━━━ ARTISTS & GENRES ━━━*
`/artists` — List all artists
`/artist <name>` — Show artist details
`/newartist <description>` — Create new artist
`/newgenre <description>` — Create new genre

*━━━ CATALOG ━━━*
`/catalog` — Recent songs
`/top` — Top-rated songs
`/search <term>` — Search songs
`/rate <id> <1-5>` — Rate a song

*━━━ STATS & QUEUE ━━━*
`/stats` — Generation statistics
`/queue` — View queue
`/qadd <artist> <concept>` — Add to queue
`/qrun` — Process queue
`/qclear` — Clear queue

*━━━ TEMPLATES ━━━*
`/templates` — List templates
`/tload <name>` — Load template
`/tsave <name>` — Save current settings

*━━━ EXAMPLES ━━━*
`/generate nova summer vibes --quality high`
`/fusion country trap yeehaw in the club`
`/like "The Weeknd" midnight city`
`/album rust "trucker's journey"`"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')


# ═══════════════════════════════════════════════════════════════
# ARTIST & GENRE COMMANDS
# ═══════════════════════════════════════════════════════════════

async def list_artists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List available artists"""
    output, _, _ = run_generate(["--list"], timeout=30)
    await update.message.reply_text(f"```\n{clean_for_telegram(output)}\n```", parse_mode='Markdown')


async def show_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show artist details"""
    if not context.args:
        await update.message.reply_text("Usage: `/artist <name>`\nExample: `/artist nova`", parse_mode='Markdown')
        return
    
    artist = context.args[0].lower()
    output, _, _ = run_generate(["--show", artist], timeout=30)
    await update.message.reply_text(f"```\n{clean_for_telegram(output)}\n```", parse_mode='Markdown')


async def create_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create new AI artist"""
    if not context.args:
        await update.message.reply_text(
            "Usage: `/newartist <description>`\n"
            "Example: `/newartist dark synthwave 80s neon noir vibes`",
            parse_mode='Markdown'
        )
        return
    
    description = ' '.join(context.args)
    await update.message.reply_text(f"🎤 Creating new artist: _{description}_\n\nThis may take a minute...", parse_mode='Markdown')
    
    output, _, _ = run_generate(["--artist", description], timeout=120)
    await update.message.reply_text(f"```\n{clean_for_telegram(output)}\n```", parse_mode='Markdown')


async def create_genre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create new genre guide"""
    if not context.args:
        await update.message.reply_text(
            "Usage: `/newgenre <description>`\n"
            "Example: `/newgenre vaporwave aesthetic lo-fi`",
            parse_mode='Markdown'
        )
        return
    
    description = ' '.join(context.args)
    await update.message.reply_text(f"🎵 Creating genre guide: _{description}_\n\nThis may take a minute...", parse_mode='Markdown')
    
    output, _, _ = run_generate(["--genre", description], timeout=120)
    await update.message.reply_text(f"```\n{clean_for_telegram(output)}\n```", parse_mode='Markdown')


# ═══════════════════════════════════════════════════════════════
# GENERATION COMMANDS
# ═══════════════════════════════════════════════════════════════

async def generate_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a song"""
    user_id = update.effective_user.id
    
    if user_id in active_generations:
        await update.message.reply_text("⏳ You already have a generation in progress. Please wait.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage: `/generate <artist> <concept> [options]`\n"
            "Example: `/generate nova summer vibes --quality high`",
            parse_mode='Markdown'
        )
        return
    
    full_text = ' '.join(context.args)
    args = parse_args(full_text)
    
    if len(args) < 2:
        await update.message.reply_text("❌ Please provide both artist and concept")
        return
    
    artist = args[0]
    concept_parts = []
    options = []
    in_options = False
    for arg in args[1:]:
        if arg.startswith('--'):
            in_options = True
        if in_options:
            options.append(arg)
        else:
            concept_parts.append(arg)
    
    concept = ' '.join(concept_parts)
    
    active_generations[user_id] = datetime.now()
    
    await update.message.reply_text(
        f"🎵 Generating: *{artist}* — _{concept}_\n"
        f"Options: {' '.join(options) if options else 'default'}\n\n"
        "This may take 2-5 minutes...",
        parse_mode='Markdown'
    )
    
    try:
        gen_args = [artist, concept] + options
        output, audio_file, all_files = run_generate(gen_args, timeout=600)
        
        # Send summary
        summary = clean_for_telegram(output, 2000)
        await update.message.reply_text(f"```\n{summary}\n```", parse_mode='Markdown')
        
        # Send audio
        if all_files:
            await send_audio_files(update, all_files, concept[:30], artist)
        else:
            await update.message.reply_text("⚠️ Generation complete but no audio file found")
            
    except Exception as e:
        logger.error(f"Generation error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        active_generations.pop(user_id, None)


async def collab_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collaboration mode - two artists, one song"""
    user_id = update.effective_user.id
    
    if user_id in active_generations:
        await update.message.reply_text("⏳ Generation in progress.")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage: `/collab <artist1> <artist2> <concept>`\n"
            "Example: `/collab ghost velvet toxic love`",
            parse_mode='Markdown'
        )
        return
    
    full_text = ' '.join(context.args)
    args = parse_args(full_text)
    
    artist1 = args[0]
    artist2 = args[1]
    concept = ' '.join(args[2:])
    
    active_generations[user_id] = datetime.now()
    
    await update.message.reply_text(
        f"🎭 *Collaboration*: {artist1} × {artist2}\n"
        f"Concept: _{concept}_\n\n"
        "This may take a few minutes...",
        parse_mode='Markdown'
    )
    
    try:
        output, audio_file, all_files = run_generate(["--collab", artist1, artist2, concept], timeout=600)
        await update.message.reply_text(f"```\n{clean_for_telegram(output, 2000)}\n```", parse_mode='Markdown')
        
        if all_files:
            await send_audio_files(update, all_files, concept[:30], f"{artist1} ft. {artist2}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        active_generations.pop(user_id, None)


async def battle_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Battle mode - same concept, two versions"""
    user_id = update.effective_user.id
    
    if user_id in active_generations:
        await update.message.reply_text("⏳ Generation in progress.")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage: `/battle <artist1> <artist2> <concept>`\n"
            "Example: `/battle blade phoenix rise up anthem`",
            parse_mode='Markdown'
        )
        return
    
    full_text = ' '.join(context.args)
    args = parse_args(full_text)
    
    artist1 = args[0]
    artist2 = args[1]
    concept = ' '.join(args[2:])
    
    active_generations[user_id] = datetime.now()
    
    await update.message.reply_text(
        f"⚔️ *Battle Mode*: {artist1} vs {artist2}\n"
        f"Concept: _{concept}_\n\n"
        "Generating both versions... this takes a while!",
        parse_mode='Markdown'
    )
    
    try:
        output, _, all_files = run_generate(["--battle", artist1, artist2, concept], timeout=900)
        await update.message.reply_text(f"```\n{clean_for_telegram(output, 2000)}\n```", parse_mode='Markdown')
        
        if all_files:
            for i, f in enumerate(all_files):
                artist = artist1 if i == 0 else artist2
                with open(f, 'rb') as af:
                    await update.message.reply_audio(
                        audio=af,
                        title=f"{concept[:25]} ({artist})",
                        performer=artist,
                        caption=f"⚔️ {artist}'s version"
                    )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        active_generations.pop(user_id, None)


async def album_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Album mode - 4-5 song EP"""
    user_id = update.effective_user.id
    
    if user_id in active_generations:
        await update.message.reply_text("⏳ Generation in progress.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/album <artist> <theme>`\n"
            "Example: `/album rust trucker's journey across america`",
            parse_mode='Markdown'
        )
        return
    
    full_text = ' '.join(context.args)
    args = parse_args(full_text)
    
    artist = args[0]
    theme = ' '.join(args[1:])
    
    active_generations[user_id] = datetime.now()
    
    await update.message.reply_text(
        f"💿 *Album Mode*: {artist}\n"
        f"Theme: _{theme}_\n\n"
        "⚠️ This generates 4-5 songs — may take 15-20 minutes!",
        parse_mode='Markdown'
    )
    
    try:
        output, _, all_files = run_generate(["--album", artist, theme], timeout=1800)
        
        # Send summary in chunks if needed
        if len(output) > 4000:
            for i in range(0, len(output), 4000):
                chunk = clean_for_telegram(output[i:i+4000])
                await update.message.reply_text(f"```\n{chunk}\n```", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"```\n{clean_for_telegram(output)}\n```", parse_mode='Markdown')
        
        # Send all audio files
        if all_files:
            await update.message.reply_text(f"📤 Uploading {len(all_files)} tracks...")
            for i, f in enumerate(all_files):
                with open(f, 'rb') as af:
                    await update.message.reply_audio(
                        audio=af,
                        title=f"Track {i+1}",
                        performer=artist,
                        caption=f"💿 {artist} — Track {i+1}"
                    )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        active_generations.pop(user_id, None)


async def vibe_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vibe mode - auto-pick artist by mood"""
    user_id = update.effective_user.id
    
    if user_id in active_generations:
        await update.message.reply_text("⏳ Generation in progress.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/vibe <mood> <concept>`\n"
            'Example: `/vibe "late night sad hours" missing someone`',
            parse_mode='Markdown'
        )
        return
    
    full_text = ' '.join(context.args)
    args = parse_args(full_text)
    
    mood = args[0]
    concept = ' '.join(args[1:])
    
    active_generations[user_id] = datetime.now()
    
    await update.message.reply_text(
        f"🎯 *Vibe Mode*\n"
        f"Mood: _{mood}_\n"
        f"Concept: _{concept}_\n\n"
        "Finding the perfect artist...",
        parse_mode='Markdown'
    )
    
    try:
        output, audio_file, all_files = run_generate(["--vibe", mood, concept], timeout=600)
        await update.message.reply_text(f"```\n{clean_for_telegram(output, 2000)}\n```", parse_mode='Markdown')
        
        if all_files:
            await send_audio_files(update, all_files, concept[:30], "Vibe Match")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        active_generations.pop(user_id, None)


async def fusion_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genre fusion mode"""
    user_id = update.effective_user.id
    
    if user_id in active_generations:
        await update.message.reply_text("⏳ Generation in progress.")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage: `/fusion <genre1> <genre2> <concept>`\n"
            "Example: `/fusion country trap yeehaw in the club`",
            parse_mode='Markdown'
        )
        return
    
    full_text = ' '.join(context.args)
    args = parse_args(full_text)
    
    genre1 = args[0]
    genre2 = args[1]
    concept = ' '.join(args[2:])
    
    active_generations[user_id] = datetime.now()
    
    await update.message.reply_text(
        f"🔀 *Genre Fusion*: {genre1} + {genre2}\n"
        f"Concept: _{concept}_\n\n"
        "Mixing genres...",
        parse_mode='Markdown'
    )
    
    try:
        output, audio_file, all_files = run_generate(["--fusion", genre1, genre2, concept], timeout=600)
        await update.message.reply_text(f"```\n{clean_for_telegram(output, 2000)}\n```", parse_mode='Markdown')
        
        if all_files:
            await send_audio_files(update, all_files, concept[:30], f"{genre1} x {genre2}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        active_generations.pop(user_id, None)


async def like_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sound-alike mode"""
    user_id = update.effective_user.id
    
    if user_id in active_generations:
        await update.message.reply_text("⏳ Generation in progress.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            'Usage: `/like <artist> <concept>`\n'
            'Example: `/like "The Weeknd" midnight city drive`',
            parse_mode='Markdown'
        )
        return
    
    full_text = ' '.join(context.args)
    args = parse_args(full_text)
    
    real_artist = args[0]
    concept = ' '.join(args[1:])
    
    active_generations[user_id] = datetime.now()
    
    await update.message.reply_text(
        f"🎭 *Sound-Alike*: {real_artist}\n"
        f"Concept: _{concept}_\n\n"
        "Analyzing style...",
        parse_mode='Markdown'
    )
    
    try:
        output, audio_file, all_files = run_generate(["--like", real_artist, concept], timeout=600)
        await update.message.reply_text(f"```\n{clean_for_telegram(output, 2000)}\n```", parse_mode='Markdown')
        
        if all_files:
            await send_audio_files(update, all_files, concept[:30], f"Like {real_artist}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        active_generations.pop(user_id, None)


async def remix_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remix mode - existing song with new artist style"""
    user_id = update.effective_user.id
    
    if user_id in active_generations:
        await update.message.reply_text("⏳ Generation in progress.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/remix <song_id> <artist>`\n"
            "Example: `/remix 1738640123 nova`",
            parse_mode='Markdown'
        )
        return
    
    song_id = context.args[0]
    artist = context.args[1]
    
    active_generations[user_id] = datetime.now()
    
    await update.message.reply_text(
        f"🔄 *Remix Mode*\n"
        f"Song: #{song_id}\n"
        f"New style: {artist}\n\n"
        "Remixing...",
        parse_mode='Markdown'
    )
    
    try:
        output, audio_file, all_files = run_generate(["--remix", song_id, artist], timeout=600)
        await update.message.reply_text(f"```\n{clean_for_telegram(output, 2000)}\n```", parse_mode='Markdown')
        
        if all_files:
            await send_audio_files(update, all_files, f"Remix #{song_id}", f"{artist} remix")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        active_generations.pop(user_id, None)


async def reroll_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reroll - regenerate with new seed"""
    user_id = update.effective_user.id
    
    if user_id in active_generations:
        await update.message.reply_text("⏳ Generation in progress.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage: `/reroll <song_id>`\n"
            "Example: `/reroll 1738640123`",
            parse_mode='Markdown'
        )
        return
    
    song_id = context.args[0]
    
    active_generations[user_id] = datetime.now()
    
    await update.message.reply_text(
        f"🎲 *Reroll*: #{song_id}\n\n"
        "Regenerating with new seed...",
        parse_mode='Markdown'
    )
    
    try:
        output, audio_file, all_files = run_generate(["--reroll", song_id], timeout=600)
        await update.message.reply_text(f"```\n{clean_for_telegram(output, 2000)}\n```", parse_mode='Markdown')
        
        if all_files:
            await send_audio_files(update, all_files, f"Reroll #{song_id}", "Reroll")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        active_generations.pop(user_id, None)


async def lyrics_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lyrics-first mode"""
    user_id = update.effective_user.id
    
    if user_id in active_generations:
        await update.message.reply_text("⏳ Generation in progress.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage: `/lyrics <your lyrics>`\n"
            "Paste your lyrics and we'll match the best artist!",
            parse_mode='Markdown'
        )
        return
    
    lyrics = ' '.join(context.args)
    
    active_generations[user_id] = datetime.now()
    
    await update.message.reply_text(
        f"📝 *Lyrics-First Mode*\n\n"
        "Matching your lyrics to the best artist...",
        parse_mode='Markdown'
    )
    
    try:
        output, audio_file, all_files = run_generate(["--lyrics", lyrics], timeout=600)
        await update.message.reply_text(f"```\n{clean_for_telegram(output, 2000)}\n```", parse_mode='Markdown')
        
        if all_files:
            await send_audio_files(update, all_files, "Custom Lyrics", "Lyrics Match")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        active_generations.pop(user_id, None)


# ═══════════════════════════════════════════════════════════════
# CATALOG COMMANDS
# ═══════════════════════════════════════════════════════════════

async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent songs"""
    output, _, _ = run_generate(["--catalog"], timeout=30)
    await update.message.reply_text(f"```\n{clean_for_telegram(output)}\n```", parse_mode='Markdown')


async def show_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show top-rated songs"""
    output, _, _ = run_generate(["--catalog", "--top"], timeout=30)
    await update.message.reply_text(f"```\n{clean_for_telegram(output)}\n```", parse_mode='Markdown')


async def search_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search songs"""
    if not context.args:
        await update.message.reply_text("Usage: `/search <term>`", parse_mode='Markdown')
        return
    
    term = ' '.join(context.args)
    output, _, _ = run_generate(["--catalog", "--search", term], timeout=30)
    await update.message.reply_text(f"```\n{clean_for_telegram(output)}\n```", parse_mode='Markdown')


async def rate_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rate a song"""
    if len(context.args) != 2:
        await update.message.reply_text("Usage: `/rate <song_id> <1-5>`", parse_mode='Markdown')
        return
    
    song_id = context.args[0]
    rating = context.args[1]
    
    output, _, _ = run_generate(["--rate", song_id, rating], timeout=30)
    await update.message.reply_text(clean_for_telegram(output))


# ═══════════════════════════════════════════════════════════════
# STATS & QUEUE COMMANDS
# ═══════════════════════════════════════════════════════════════

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show generation statistics"""
    args = ["--stats"]
    if context.args:
        args.extend(["--artist", context.args[0]])
    
    output, _, _ = run_generate(args, timeout=30)
    await update.message.reply_text(f"```\n{clean_for_telegram(output)}\n```", parse_mode='Markdown')


async def show_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show queue"""
    output, _, _ = run_generate(["--queue", "list"], timeout=30)
    await update.message.reply_text(f"```\n{clean_for_telegram(output)}\n```", parse_mode='Markdown')


async def queue_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add to queue"""
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/qadd <artist> <concept> [options]`\n"
            "Example: `/qadd nova summer vibes --quality high`",
            parse_mode='Markdown'
        )
        return
    
    full_text = ' '.join(context.args)
    args = parse_args(full_text)
    
    artist = args[0]
    concept = ' '.join(args[1:])
    
    output, _, _ = run_generate(["--queue", "add", artist, concept], timeout=30)
    await update.message.reply_text(clean_for_telegram(output))


async def queue_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Run queue"""
    user_id = update.effective_user.id
    
    if user_id in active_generations:
        await update.message.reply_text("⏳ Generation in progress.")
        return
    
    active_generations[user_id] = datetime.now()
    
    await update.message.reply_text("🚀 Processing queue... this may take a while!")
    
    try:
        output, _, all_files = run_generate(["--queue", "run"], timeout=3600)
        
        # Send output in chunks
        for i in range(0, len(output), 4000):
            chunk = clean_for_telegram(output[i:i+4000])
            await update.message.reply_text(f"```\n{chunk}\n```", parse_mode='Markdown')
        
        # Send all audio files
        if all_files:
            await update.message.reply_text(f"📤 Uploading {len(all_files)} songs...")
            for i, f in enumerate(all_files):
                with open(f, 'rb') as af:
                    await update.message.reply_audio(audio=af, title=f"Queue Song {i+1}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        active_generations.pop(user_id, None)


async def queue_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear queue"""
    output, _, _ = run_generate(["--queue", "clear"], timeout=30)
    await update.message.reply_text(clean_for_telegram(output))


# ═══════════════════════════════════════════════════════════════
# TEMPLATE COMMANDS
# ═══════════════════════════════════════════════════════════════

async def template_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List templates"""
    output, _, _ = run_generate(["--template", "list"], timeout=30)
    await update.message.reply_text(f"```\n{clean_for_telegram(output)}\n```", parse_mode='Markdown')


async def template_load(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Load template"""
    if not context.args:
        await update.message.reply_text("Usage: `/tload <name>`", parse_mode='Markdown')
        return
    
    name = context.args[0]
    output, _, _ = run_generate(["--template", "load", name], timeout=30)
    await update.message.reply_text(clean_for_telegram(output))


async def template_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save template"""
    if not context.args:
        await update.message.reply_text(
            "Usage: `/tsave <name> [options]`\n"
            "Example: `/tsave radio-ready --quality high --master`",
            parse_mode='Markdown'
        )
        return
    
    full_text = ' '.join(context.args)
    args = parse_args(full_text)
    name = args[0]
    options = args[1:] if len(args) > 1 else []
    
    cmd_args = ["--template", "save", name] + options
    output, _, _ = run_generate(cmd_args, timeout=30)
    await update.message.reply_text(clean_for_telegram(output))


# ═══════════════════════════════════════════════════════════════
# ERROR HANDLER
# ═══════════════════════════════════════════════════════════════

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text("❌ An error occurred. Please try again.")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    """Start the bot"""
    print("🎵 Starting Music Planner Telegram Bot v3.0...")
    print(f"Script directory: {SCRIPT_DIR}")
    print(f"Generate script: {GENERATE_SCRIPT}")
    
    if not GENERATE_SCRIPT.exists():
        print(f"❌ Error: {GENERATE_SCRIPT} not found!")
        sys.exit(1)
    
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Basic commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    
    # Artist & Genre
    app.add_handler(CommandHandler("artists", list_artists))
    app.add_handler(CommandHandler("artist", show_artist))
    app.add_handler(CommandHandler("newartist", create_artist))
    app.add_handler(CommandHandler("newgenre", create_genre))
    
    # Generation modes
    app.add_handler(CommandHandler("generate", generate_song))
    app.add_handler(CommandHandler("g", generate_song))
    app.add_handler(CommandHandler("collab", collab_song))
    app.add_handler(CommandHandler("battle", battle_song))
    app.add_handler(CommandHandler("album", album_song))
    app.add_handler(CommandHandler("vibe", vibe_song))
    app.add_handler(CommandHandler("fusion", fusion_song))
    app.add_handler(CommandHandler("like", like_song))
    app.add_handler(CommandHandler("remix", remix_song))
    app.add_handler(CommandHandler("reroll", reroll_song))
    app.add_handler(CommandHandler("lyrics", lyrics_song))
    
    # Catalog
    app.add_handler(CommandHandler("catalog", show_catalog))
    app.add_handler(CommandHandler("top", show_top))
    app.add_handler(CommandHandler("search", search_catalog))
    app.add_handler(CommandHandler("rate", rate_song))
    
    # Stats & Queue
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("queue", show_queue))
    app.add_handler(CommandHandler("qadd", queue_add))
    app.add_handler(CommandHandler("qrun", queue_run))
    app.add_handler(CommandHandler("qclear", queue_clear))
    
    # Templates
    app.add_handler(CommandHandler("templates", template_list))
    app.add_handler(CommandHandler("tload", template_load))
    app.add_handler(CommandHandler("tsave", template_save))
    
    # Error handler
    app.add_error_handler(error_handler)
    
    print("✅ Bot is running! Press Ctrl+C to stop.")
    print("Commands registered: start, help, artists, artist, newartist, newgenre,")
    print("  generate, g, collab, battle, album, vibe, fusion, like, remix, reroll, lyrics,")
    print("  catalog, top, search, rate, stats, queue, qadd, qrun, qclear, templates, tload, tsave")
    
    # Run the bot
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
