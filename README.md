# 🎵 Music Planner v3.0

AI Artist Management & Automated Song Generation with Production Quality Tools

## Overview

Create AI Artists with distinct personalities, then generate songs with a single command. Ollama writes the lyrics, ACE-Step generates the music. Includes quality presets, multi-take generation, mastering, batch queue, and a Telegram bot.

**Stack:**
- **Ollama** (llama3.2) — Lyrics generation, artist/genre creation, style analysis
- **ACE-Step** — AI music generation
- **FFmpeg** — Audio mastering (optional)
- **Telegram Bot** — Generate music from your phone

## Quick Start

```bash
cd music_planner

# Generate a song
./generate.sh nova "a song about city lights at midnight"

# High quality with mastering
./generate.sh nova "epic anthem" --quality high --master

# Generate 5 takes, pick the best
./generate.sh ghost "dark banger" --takes 5

# List all artists
./generate.sh --list

# See all options
./generate.sh --help
```

## 🎛️ Production Quality

### Quality Presets
```bash
./generate.sh nova "test" --quality draft    # Fast preview (27 steps)
./generate.sh nova "test" --quality normal   # Default (60 steps)
./generate.sh nova "test" --quality high     # Better (100 steps, pingpong)
./generate.sh nova "test" --quality ultra    # Best (150 steps, heun, FLAC)
```

| Preset | Steps | Scheduler | Format | Use Case |
|--------|-------|-----------|--------|----------|
| draft | 27 | euler | mp3 | Quick preview |
| normal | 60 | euler | mp3 | Default |
| high | 100 | pingpong | mp3 | Better consistency |
| ultra | 150 | heun | flac | Final master |

### Multi-Take Generation
ACE-Step output varies with random seeds ("gacha-style"). Generate multiple takes to beat the RNG:

```bash
./generate.sh ghost "midnight trap" --takes 5
# Generates 5 versions with different seeds - pick your favorite!
```

### Mastering
Apply post-processing for streaming-ready output:

```bash
./generate.sh nova "radio hit" --quality ultra --master
```

Mastering chain:
- High-pass filter (30Hz) — removes rumble
- Gentle compression — evens dynamics
- Limiter (-1dB) — prevents clipping
- EBU R128 normalization (-14 LUFS) — streaming standard

### Reroll
Like the concept but not the take? Regenerate with a new seed:

```bash
./generate.sh --reroll 1738640123
```

## 🎤 Generation Modes

### Basic Generation
```bash
./generate.sh <artist> "<concept>"
```

### Collaboration
```bash
./generate.sh --collab ghost velvet "toxic love that feels so good"
```

### Battle Mode
```bash
./generate.sh --battle blade phoenix "unstoppable rise"
```

### Album Mode
```bash
./generate.sh --album rust "a trucker's journey across america"
```
Generates a 5-song EP with narrative arc.

### Vibe Mode
```bash
./generate.sh --vibe "aggressive workout energy" "champion anthem"
```
Auto-picks the best-matching artist.

### Genre Fusion
```bash
./generate.sh --fusion country trap "yeehaw in the club"
./generate.sh --fusion jazz electronic "midnight cyberlounge"
```
Blends two genres into one unique sound.

### Sound-Alike
```bash
./generate.sh --like "The Weeknd" "neon city heartbreak"
./generate.sh --like "Taylor Swift" "autumn memories"
```
Analyzes a real artist's style and generates matching tags.

### Remix Mode
```bash
./generate.sh --remix <song_id> nova
```

### Lyrics-First
```bash
./generate.sh --lyrics "your complete lyrics here"
```

## 📊 Ratings & Statistics

### Rate Songs
```bash
./generate.sh --rate 1738640123 5    # 1-5 stars
./generate.sh --catalog --top         # View top-rated
```

### Generation Stats
```bash
./generate.sh --stats                 # Overall statistics
./generate.sh --stats --artist nova   # Per-artist breakdown
```

## 📋 Queue (Batch Generation)

Queue up songs and process them all at once (great for overnight batches):

```bash
# Add to queue
./generate.sh --queue add nova "summer anthem" --quality high
./generate.sh --queue add ghost "midnight trap"
./generate.sh --queue add velvet "slow jam" --master

# View queue
./generate.sh --queue list

# Process entire queue
./generate.sh --queue run

# Clear queue
./generate.sh --queue clear
```

## 📑 Templates

Save your favorite settings:

```bash
# Save current settings
./generate.sh --template save radio-ready --quality high --master --takes 3

# List templates
./generate.sh --template list

# Load and use
./generate.sh --template load radio-ready
./generate.sh nova "hit single"   # Uses loaded settings
```

## 🤖 Telegram Bot

Generate music from anywhere via Telegram! **100% autonomous** — runs without any external AI APIs.

### Start the Bot
```bash
./start_bot.sh
# Or: python3 telegram_bot.py
```

### Bot Commands

**Generation:**
- `/generate <artist> <concept>` — Basic generation
- `/g` — Shortcut for /generate
- `/collab <a1> <a2> <concept>` — Two artists collaborate
- `/battle <a1> <a2> <concept>` — Same concept, two versions
- `/album <artist> <theme>` — Generate 4-5 song EP
- `/vibe <mood> <concept>` — Auto-pick artist
- `/fusion <g1> <g2> <concept>` — Genre fusion
- `/like <artist> <concept>` — Sound-alike mode
- `/remix <song_id> <artist>` — Remix with new style
- `/reroll <song_id>` — Regenerate with new seed
- `/lyrics <text>` — Match your lyrics to an artist

**Artists & Genres:**
- `/artists` — List all artists
- `/artist <name>` — Artist details
- `/newartist <description>` — Create AI artist
- `/newgenre <description>` — Create genre guide

**Catalog:**
- `/catalog` — Recent songs
- `/top` — Top-rated songs
- `/search <term>` — Search songs
- `/rate <id> <1-5>` — Rate a song

**Queue & Templates:**
- `/queue` / `/qadd` / `/qrun` / `/qclear`
- `/templates` / `/tload` / `/tsave`

**Options (add after concept):**
- `--quality draft|normal|high|ultra`
- `--takes N`
- `--master`

### Examples
```
/generate nova summer vibes --quality high
/fusion country trap yeehaw in the club
/like "The Weeknd" midnight city
/album rust trucker's journey
/newartist dark synthwave neon noir
```

### Architecture
```
Telegram → telegram_bot.py → generate.sh → Ollama (lyrics)
                                        → ACE-Step (music)
```
No Claude/Anthropic involved — fully autonomous!

## 📚 Catalog

```bash
./generate.sh --catalog                    # All songs
./generate.sh --catalog --artist nova      # Filter by artist
./generate.sh --catalog --search "love"    # Search lyrics/concepts
./generate.sh --catalog --top              # Top-rated songs
```

## ✨ Create Content

### New Artist
```bash
./generate.sh --artist "a melancholic indie folk singer who writes about nature"
```

### New Genre Guide
```bash
./generate.sh --genre "vaporwave aesthetic lo-fi with city pop influences"
```

## 🎤 Artist Roster

| Artist | Vibe | Genre | Voice |
|--------|------|-------|-------|
| **NOVA** | Dreamy, ethereal | Synth-pop | Female, airy |
| **BLADE** | Aggressive, confident | Trap, drill | Male, hard |
| **VELVET** | Smooth, sensual | R&B, neo-soul | Female, silky |
| **RUST** | Weathered, authentic | Country rock | Male, raspy |
| **ECHO** | Calm, meditative | Lo-fi, ambient | Instrumental |
| **PHOENIX** | Powerful, triumphant | Rock | Female, soaring |
| **GHOST** | Dark, melodic | Melodic trap | Male, autotune |
| **ZEPHYR WYNTON** | Neon-noir, haunting | Synthwave | Male, ethereal |

## 🖥️ Web Dashboard

```bash
cd dashboard
./run.sh
# Opens at http://localhost:5555
```

## Directory Structure

```
music_planner/
├── generate.sh         # Main CLI tool
├── telegram_bot.py     # Telegram bot
├── start_bot.sh        # Bot launcher
├── artists/            # Artist profiles (.md)
├── catalog/
│   └── songs.json      # Song database
├── templates/          # Saved setting templates
├── queue.json          # Generation queue
├── stats.json          # Generation statistics
└── dashboard/          # Web UI
```

## Configuration

Environment variables:
```bash
OLLAMA_HOST=localhost        # Ollama server (default: localhost)
OLLAMA_PORT=11434            # Ollama port (default: 11434)
OLLAMA_MODEL=llama3.2        # Model for lyrics (default: llama3.2)
ACESTEP_BIN=~/bin/acestep    # ACE-Step CLI path
TELEGRAM_BOT_TOKEN=xxx       # Bot token (required for Telegram bot)
```

## CLI Options

```
--quality <preset>   draft|normal|high|ultra
--takes <n>          Generate N versions
--master             Apply mastering
--duration <secs>    Song length (default: 120)
--steps <n>          Override inference steps
--scheduler <type>   euler|heun|pingpong
--seed <n>           Manual seed for reproducibility
--model <model>      Override Ollama model
```

---

*Built for Jack & Jill's music experiments* 🎹
