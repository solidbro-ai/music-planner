#!/bin/bash
# Music Planner v3.0 - Full-Featured AI Music Generation
# Features: Artists, Lyrics, Catalog, Collabs, Albums, Battles, Remixes, Vibes
#           Genre Fusion, Sound-Alike, Ratings, Stats, Queue, Templates

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTISTS_DIR="$SCRIPT_DIR/artists"
CATALOG_DIR="$SCRIPT_DIR/catalog"
CATALOG_FILE="$CATALOG_DIR/songs.json"
TEMPLATES_DIR="$SCRIPT_DIR/templates"
QUEUE_FILE="$SCRIPT_DIR/queue.json"
STATS_FILE="$SCRIPT_DIR/stats.json"
GENRES_DIR="$SCRIPT_DIR/../ACESTEP_genres"
ACESTEP_BIN="${ACESTEP_BIN:-$HOME/bin/acestep}"

# Ollama config
OLLAMA_HOST="${OLLAMA_HOST:-10.10.10.13}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:30b-a3b-q4_K_M}"
OLLAMA_URL="http://${OLLAMA_HOST}:${OLLAMA_PORT}/api/generate"

# Defaults
DURATION=120
STEPS=60
FORMAT="mp3"
QUALITY="normal"
TAKES=1
MASTER=false
SCHEDULER="euler"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

usage() {
    cat << EOF
🎵 Music Planner v3.0 - AI Artist Song Generator

BASIC USAGE:
  ./generate.sh <artist> "<concept>"         Generate song with artist
  ./generate.sh --list                       List all artists
  ./generate.sh --show <artist>              Show artist details

CREATE NEW:
  ./generate.sh --artist "<description>"     Create new artist with AI
  ./generate.sh --genre "<description>"      Create new genre guide with AI

ADVANCED MODES:
  ./generate.sh --collab <artist1> <artist2> "<concept>"
                                             Two artists collaborate
  ./generate.sh --battle <artist1> <artist2> "<concept>"
                                             Battle: both artists, same concept
  ./generate.sh --album <artist> "<theme>"   Generate 4-5 song EP
  ./generate.sh --vibe "<mood>" "<concept>"  Auto-pick artist by mood
  ./generate.sh --remix <song_id> <new_artist>
                                             Remix existing song with new artist
  ./generate.sh --lyrics "<your lyrics>"     Match lyrics to best artist
  ./generate.sh --fusion <genre1> <genre2> "<concept>"
                                             Fuse two genres into one song
  ./generate.sh --like "<real artist>" "<concept>"
                                             Generate in style of real artist

CATALOG & RATINGS:
  ./generate.sh --catalog                    List all generated songs
  ./generate.sh --catalog --artist <name>    Filter by artist
  ./generate.sh --catalog --search "<term>"  Search songs
  ./generate.sh --catalog --top              Show top-rated songs
  ./generate.sh --rate <song_id> <1-5>       Rate a song (1-5 stars)

STATS:
  ./generate.sh --stats                      Show generation statistics
  ./generate.sh --stats --artist <name>      Stats for specific artist

QUEUE (Batch Generation):
  ./generate.sh --queue add <artist> "<concept>"   Add to queue
  ./generate.sh --queue list                       Show queue
  ./generate.sh --queue run                        Process entire queue
  ./generate.sh --queue clear                      Clear queue

TEMPLATES:
  ./generate.sh --template save <name>       Save current settings as template
  ./generate.sh --template load <name>       Load and apply template
  ./generate.sh --template list              List saved templates
  ./generate.sh --template show <name>       Show template details

PRODUCTION:
  ./generate.sh --reroll <song_id>           Regenerate song with new seed

OPTIONS:
  --quality <preset>  Quality preset: draft|normal|high|ultra (default: normal)
  --takes <n>         Generate N versions with different seeds (default: 1)
  --master            Apply post-processing (loudness norm, limiting)
  --duration <secs>   Song duration (default: 120)
  --steps <n>         Override inference steps
  --scheduler <type>  Scheduler: euler|heun|pingpong
  --seed <n>          Manual seed for reproducibility
  --model <model>     Ollama model (default: llama3.2)
  -h, --help          Show this help

EXAMPLES:
  ./generate.sh nova "a song about city lights"
  ./generate.sh nova "epic anthem" --quality ultra --master
  ./generate.sh ghost "dark trap banger" --takes 5 --quality high
  ./generate.sh --fusion country trap "yeehaw in the club"
  ./generate.sh --like "The Weeknd" "midnight drive through the city"
  ./generate.sh --rate 1738640123 5
  ./generate.sh --queue add nova "summer vibes" && ./generate.sh --queue run
  ./generate.sh --template save radio-ready --quality high --master
EOF
}

# Initialize catalog
init_catalog() {
    mkdir -p "$CATALOG_DIR"
    if [[ ! -f "$CATALOG_FILE" ]]; then
        echo '{"songs": []}' > "$CATALOG_FILE"
    fi
}

# Apply quality preset
apply_quality_preset() {
    local preset="$1"
    case "$preset" in
        draft)
            STEPS=27
            SCHEDULER="euler"
            FORMAT="mp3"
            ;;
        normal)
            STEPS=60
            SCHEDULER="euler"
            FORMAT="mp3"
            ;;
        high)
            STEPS=100
            SCHEDULER="pingpong"
            FORMAT="mp3"
            ;;
        ultra)
            STEPS=150
            SCHEDULER="heun"
            FORMAT="flac"
            ;;
        *)
            echo -e "${RED}❌ Unknown quality preset: $preset${NC}"
            echo -e "${YELLOW}Available: draft, normal, high, ultra${NC}"
            exit 1
            ;;
    esac
}

# Post-processing / Mastering
master_audio() {
    local input_file="$1"
    local output_file="${input_file%.*}_mastered.${input_file##*.}"
    
    echo -e "${CYAN}🎛️  Mastering: $input_file${NC}"
    
    # Check if ffmpeg is available
    if ! command -v ffmpeg &> /dev/null; then
        echo -e "${RED}❌ ffmpeg not found, skipping mastering${NC}"
        return 1
    fi
    
    # Mastering chain:
    # 1. High-pass filter at 30Hz (remove rumble)
    # 2. Gentle compression (threshold -20dB, ratio 4:1)
    # 3. Limiter at -1dB
    # 4. EBU R128 loudness normalization to -14 LUFS (streaming standard)
    
    # First pass: analyze loudness
    local loudness_info=$(ffmpeg -i "$input_file" -af "loudnorm=I=-14:TP=-1:LRA=11:print_format=json" -f null - 2>&1 | grep -A 20 "input_i")
    
    local input_i=$(echo "$loudness_info" | grep "input_i" | grep -o '[-0-9.]*' | head -1)
    local input_tp=$(echo "$loudness_info" | grep "input_tp" | grep -o '[-0-9.]*' | head -1)
    local input_lra=$(echo "$loudness_info" | grep "input_lra" | grep -o '[-0-9.]*' | head -1)
    local input_thresh=$(echo "$loudness_info" | grep "input_thresh" | grep -o '[-0-9.]*' | head -1)
    
    # Set defaults if analysis failed
    [[ -z "$input_i" ]] && input_i="-24"
    [[ -z "$input_tp" ]] && input_tp="-2"
    [[ -z "$input_lra" ]] && input_lra="7"
    [[ -z "$input_thresh" ]] && input_thresh="-34"
    
    # Second pass: apply normalization with measured values
    ffmpeg -y -i "$input_file" -af "highpass=f=30,acompressor=threshold=-20dB:ratio=4:attack=5:release=50,loudnorm=I=-14:TP=-1:LRA=11:measured_I=$input_i:measured_TP=$input_tp:measured_LRA=$input_lra:measured_thresh=$input_thresh:linear=true" "$output_file" 2>/dev/null
    
    if [[ -f "$output_file" ]]; then
        echo -e "${GREEN}✅ Mastered: $output_file${NC}"
        # Show loudness comparison
        echo -e "${BLUE}   Original: ${input_i} LUFS → Mastered: -14 LUFS${NC}"
        echo "$output_file"
    else
        echo -e "${RED}❌ Mastering failed${NC}"
        return 1
    fi
}

# Generate random seed
generate_seed() {
    echo $((RANDOM * RANDOM))
}

# Add song to catalog
add_to_catalog() {
    local artist="$1"
    local concept="$2"
    local lyrics="$3"
    local file_path="$4"
    local tags="$5"
    local mode="${6:-standard}"
    local seed="${7:-0}"
    local quality="${8:-normal}"

    local song_id=$(date +%s%N | cut -c1-13)  # Millisecond precision for multiple takes
    local date=$(date +%Y-%m-%d)
    local time=$(date +%H:%M:%S)

    # Escape strings for JSON
    local escaped_concept=$(echo "$concept" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))")
    local escaped_lyrics=$(echo "$lyrics" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))")
    local escaped_file=$(echo "$file_path" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))")
    local escaped_tags=$(echo "$tags" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))")

    # Add to catalog using Python for reliable JSON handling
    python3 << EOF
import json
import os

catalog_file = "$CATALOG_FILE"
with open(catalog_file, 'r') as f:
    catalog = json.load(f)

song = {
    "id": "$song_id",
    "artist": "$artist",
    "concept": $escaped_concept,
    "lyrics": $escaped_lyrics,
    "file": $escaped_file,
    "tags": $escaped_tags,
    "mode": "$mode",
    "seed": $seed,
    "quality": "$quality",
    "date": "$date",
    "time": "$time"
}

catalog["songs"].append(song)

with open(catalog_file, 'w') as f:
    json.dump(catalog, f, indent=2)

print(f"Added song {$song_id} to catalog")
EOF
}

# Call Ollama API
ollama_generate() {
    local prompt="$1"
    local escaped_prompt=$(echo "$prompt" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")

    local response=$(curl -s --connect-timeout 10 --max-time 180 "$OLLAMA_URL" \
        -H "Content-Type: application/json" \
        -d "{\"model\": \"$OLLAMA_MODEL\", \"prompt\": $escaped_prompt, \"stream\": false}")

    echo "$response" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('response', ''))" 2>/dev/null
}

list_artists() {
    echo -e "${PURPLE}🎤 Available AI Artists${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    for f in "$ARTISTS_DIR"/*.md; do
        [[ -f "$f" ]] || continue
        name=$(basename "$f" .md)
        personality=$(grep "^personality:" "$f" | head -1 | sed 's/personality: *//')
        mood=$(grep "^mood:" "$f" | head -1 | sed 's/mood: *//')
        energy=$(grep "^energy:" "$f" | head -1 | sed 's/energy: *//')
        echo -e "${GREEN}$name${NC} - $personality"
        echo -e "   ${BLUE}Mood:${NC} $mood | ${BLUE}Energy:${NC} $energy"
        echo ""
    done
}

show_artist() {
    local artist="$1"
    local file="$ARTISTS_DIR/$artist.md"
    [[ -f "$file" ]] || { echo -e "${RED}❌ Artist not found${NC}"; exit 1; }
    echo -e "${PURPLE}🎤 Artist Profile: $artist${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    cat "$file"
}

show_catalog() {
    local filter_artist="$1"
    local search_term="$2"

    init_catalog

    echo -e "${PURPLE}📚 Song Catalog${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    python3 << EOF
import json

with open("$CATALOG_FILE", 'r') as f:
    catalog = json.load(f)

songs = catalog.get("songs", [])
filter_artist = "$filter_artist".lower() if "$filter_artist" else None
search_term = "$search_term".lower() if "$search_term" else None

filtered = []
for song in songs:
    if filter_artist and filter_artist not in song.get("artist", "").lower():
        continue
    if search_term:
        searchable = f"{song.get('concept','')} {song.get('lyrics','')} {song.get('artist','')}".lower()
        if search_term not in searchable:
            continue
    filtered.append(song)

if not filtered:
    print("No songs found.")
else:
    for song in filtered[-20:]:  # Show last 20
        song_id = song.get('id', 'N/A')
        print(f"\033[0;32m#{song_id}\033[0m | {song['date']} | \033[0;34m{song['artist']}\033[0m")
        concept = song.get('concept', '')[:60]
        print(f"   {concept}...")
        print(f"   📁 {song.get('file', 'N/A')}")
        mode = song.get('mode', 'standard')
        quality = song.get('quality', 'normal')
        seed = song.get('seed', 'N/A')
        print(f"   Mode: {mode} | Quality: {quality} | Seed: {seed}")
        print()

print(f"Total: {len(filtered)} songs")
print(f"\n\033[0;33m💡 Use --reroll <id> to regenerate with new seed\033[0m")
EOF
}

get_genre_context() {
    local artist_file="$1"
    local primary_genre=$(grep -A2 "^genres:" "$artist_file" | grep "^  - " | head -1 | sed 's/  - //' | tr '[:upper:]' '[:lower:]')

    for genre_file in "$GENRES_DIR"/*.md; do
        [[ -f "$genre_file" ]] || continue
        local genre_name=$(basename "$genre_file" .md)
        if [[ "$primary_genre" == *"$genre_name"* ]] || [[ "$genre_name" == *"trap"* && "$primary_genre" == *"trap"* ]]; then
            cat "$genre_file"
            return
        fi
    done

    # Fallback matches
    [[ "$primary_genre" == *"hip"* ]] && [[ -f "$GENRES_DIR/hiphop.md" ]] && cat "$GENRES_DIR/hiphop.md"
    [[ "$primary_genre" == *"r&b"* ]] && [[ -f "$GENRES_DIR/rnb.md" ]] && cat "$GENRES_DIR/rnb.md"
}

generate_lyrics() {
    local artist_file="$1"
    local concept="$2"
    local collab_file="$3"

    local artist_content=$(cat "$artist_file")
    local genre_context=$(get_genre_context "$artist_file")

    local collab_section=""
    if [[ -n "$collab_file" ]] && [[ -f "$collab_file" ]]; then
        local collab_content=$(cat "$collab_file")
        collab_section="

COLLABORATING ARTIST:
$collab_content

Write the song as a collaboration. Artist 1 does verse 1 and parts of chorus. Artist 2 does verse 2 and bridge. They share the final chorus."
    fi

    local prompt="You are a professional songwriter.

ARTIST PROFILE:
$artist_content

GENRE GUIDE:
$genre_context
$collab_section

SONG CONCEPT: $concept

Write complete song lyrics. Rules:
1. Use structure tags: [intro], [verse], [chorus], [bridge], [outro]
2. Match the artist's themes, mood, and style
3. Strong rhyme schemes (AABB, ABAB, ABCB)
4. Metaphors, wordplay, vivid imagery
5. Verses 4-8 lines, choruses 4-6 lines
6. Catchy, memorable chorus
7. If instrumental artist, output only: [instrumental]

Output ONLY lyrics with structure tags. No explanations."

    echo -e "${CYAN}🤖 Generating lyrics with Ollama...${NC}" >&2
    ollama_generate "$prompt"
}

generate_song() {
    local artist="$1"
    local concept="$2"
    local mode="${3:-standard}"
    local collab_artist="$4"
    local provided_lyrics="$5"  # Optional: pass lyrics directly (for reroll)
    local provided_seed="$6"    # Optional: specific seed (for reroll)

    local artist_file="$ARTISTS_DIR/$artist.md"
    [[ -f "$artist_file" ]] || { echo -e "${RED}❌ Artist '$artist' not found${NC}"; exit 1; }

    local artist_name=$(grep "^name:" "$artist_file" | sed 's/name: *//')
    local signature_tags=$(grep "^signature_tags:" "$artist_file" | sed 's/signature_tags: *//' | tr -d '"')

    local collab_file=""
    local display_artist="$artist_name"
    if [[ -n "$collab_artist" ]]; then
        collab_file="$ARTISTS_DIR/$collab_artist.md"
        local collab_name=$(grep "^name:" "$collab_file" | sed 's/name: *//')
        display_artist="$artist_name ft. $collab_name"
        # Blend tags
        local collab_tags=$(grep "^signature_tags:" "$collab_file" | sed 's/signature_tags: *//' | tr -d '"')
        signature_tags="$signature_tags, $collab_tags"
    fi

    echo -e "${PURPLE}🎤 Artist: $display_artist${NC}"
    echo -e "${BLUE}💭 Concept: $concept${NC}"
    echo -e "${YELLOW}🎵 Mode: $mode | Quality: $QUALITY | Takes: $TAKES${NC}"
    echo ""

    # Generate or use provided lyrics
    local lyrics
    if [[ -n "$provided_lyrics" ]]; then
        lyrics="$provided_lyrics"
        echo -e "${CYAN}📝 Using provided lyrics${NC}"
    else
        lyrics=$(generate_lyrics "$artist_file" "$concept" "$collab_file")
    fi

    echo ""
    echo -e "${PURPLE}📝 Lyrics:${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "$lyrics"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Multi-take generation
    local generated_files=()
    local take_num=1
    
    while [[ $take_num -le $TAKES ]]; do
        if [[ $TAKES -gt 1 ]]; then
            echo -e "${PURPLE}━━━ TAKE $take_num/$TAKES ━━━${NC}"
        fi
        
        # Generate seed (use provided or random)
        local seed
        if [[ -n "$provided_seed" ]] && [[ $take_num -eq 1 ]]; then
            seed="$provided_seed"
        else
            seed=$(generate_seed)
        fi
        
        echo -e "${GREEN}⏳ Generating with ACE-Step (seed: $seed)...${NC}"

        # Write lyrics to temp file to handle special characters and newlines
        local lyrics_file=$(mktemp /tmp/lyrics.XXXXXX)
        printf '%s' "$lyrics" > "$lyrics_file"
        
        # Read lyrics back for the command
        local lyrics_clean=$(cat "$lyrics_file")
        
        # Execute generation
        local output=$("$ACESTEP_BIN" -t "$signature_tags" -l "$lyrics_clean" -d "$DURATION" -s "$STEPS" -f "$FORMAT" --scheduler "$SCHEDULER" --seed "$seed" 2>&1)
        local exit_code=$?
        
        rm -f "$lyrics_file"
        
        echo "$output"
        
        # Debug: show exit code if failed
        [[ $exit_code -ne 0 ]] && echo -e "${YELLOW}ACE-Step exit code: $exit_code${NC}"

        local audio_file=$(echo "$output" | grep "AUDIO_FILE=" | cut -d= -f2)

        if [[ -n "$audio_file" ]] && [[ -f "$audio_file" ]]; then
            # Apply mastering if requested
            if [[ "$MASTER" == true ]]; then
                local mastered_file=$(master_audio "$audio_file")
                if [[ -n "$mastered_file" ]] && [[ -f "$mastered_file" ]]; then
                    audio_file="$mastered_file"
                fi
            fi
            
            generated_files+=("$audio_file")
            
            # Add to catalog
            init_catalog
            local take_mode="$mode"
            [[ $TAKES -gt 1 ]] && take_mode="$mode-take$take_num"
            add_to_catalog "$display_artist" "$concept" "$lyrics" "$audio_file" "$signature_tags" "$take_mode" "$seed" "$QUALITY"
            
            echo -e "${GREEN}✅ Take $take_num complete: $audio_file${NC}"
        else
            echo -e "${RED}❌ Take $take_num failed${NC}"
        fi
        
        ((take_num++))
        echo ""
    done
    
    # Summary for multi-take
    if [[ $TAKES -gt 1 ]] && [[ ${#generated_files[@]} -gt 0 ]]; then
        echo -e "${PURPLE}━━━ GENERATION COMPLETE ━━━${NC}"
        echo -e "${GREEN}Generated ${#generated_files[@]} takes:${NC}"
        for f in "${generated_files[@]}"; do
            echo -e "   📁 $f"
        done
        echo ""
        echo -e "${YELLOW}💡 Listen to all takes and pick your favorite!${NC}"
    fi
}

# COLLAB MODE
do_collab() {
    local artist1="$1"
    local artist2="$2"
    local concept="$3"

    echo -e "${PURPLE}🎭 COLLABORATION MODE${NC}"
    echo -e "${GREEN}$artist1${NC} × ${GREEN}$artist2${NC}"
    echo ""

    generate_song "$artist1" "$concept" "collab" "$artist2"
}

# BATTLE MODE
do_battle() {
    local artist1="$1"
    local artist2="$2"
    local concept="$3"

    echo -e "${PURPLE}⚔️  BATTLE MODE${NC}"
    echo -e "${GREEN}$artist1${NC} vs ${GREEN}$artist2${NC}"
    echo -e "${BLUE}Concept: $concept${NC}"
    echo ""

    echo -e "${YELLOW}━━━ ROUND 1: $artist1 ━━━${NC}"
    generate_song "$artist1" "$concept" "battle"

    echo ""
    echo -e "${YELLOW}━━━ ROUND 2: $artist2 ━━━${NC}"
    generate_song "$artist2" "$concept" "battle"

    echo ""
    echo -e "${PURPLE}⚔️  BATTLE COMPLETE! Listen to both and pick your winner!${NC}"
}

# ALBUM MODE
do_album() {
    local artist="$1"
    local theme="$2"

    local artist_file="$ARTISTS_DIR/$artist.md"
    [[ -f "$artist_file" ]] || { echo -e "${RED}❌ Artist not found${NC}"; exit 1; }

    local artist_name=$(grep "^name:" "$artist_file" | sed 's/name: *//')

    echo -e "${PURPLE}💿 ALBUM MODE${NC}"
    echo -e "${GREEN}Artist: $artist_name${NC}"
    echo -e "${BLUE}Theme: $theme${NC}"
    echo ""

    echo -e "${CYAN}🤖 Planning album with Ollama...${NC}"

    local album_plan=$(ollama_generate "Create a 5-song EP for artist '$artist_name' with theme: '$theme'

IMPORTANT: Output EXACTLY this format with no extra text, no markdown, no explanations:

ALBUM_TITLE: Your Album Title Here
TRACK_1: First song concept in one sentence
TRACK_2: Second song concept in one sentence
TRACK_3: Third song concept in one sentence
TRACK_4: Fourth song concept in one sentence
TRACK_5: Fifth song concept in one sentence

Rules:
- Each track must be on its own line
- Each line must start with TRACK_X: (where X is 1-5)
- Keep each concept to ONE sentence
- Make tracks flow as a narrative arc
- NO bullet points, NO numbering, NO markdown")

    echo ""
    echo -e "${YELLOW}Album Plan:${NC}"
    echo "$album_plan"
    echo ""

    # Parse tracks - more robust parsing that handles various Ollama output formats
    local tracks=()
    while IFS= read -r line; do
        # Strip leading whitespace and handle various formats
        local trimmed=$(echo "$line" | sed 's/^[[:space:]]*//')
        if [[ "$trimmed" == TRACK_* ]] || [[ "$trimmed" =~ ^TRACK_[0-9]+: ]]; then
            local track_concept=$(echo "$trimmed" | sed 's/^TRACK_[0-9]*:[[:space:]]*//')
            [[ -n "$track_concept" ]] && tracks+=("$track_concept")
        fi
    done <<< "$album_plan"

    # Fallback: if no tracks parsed, try alternative patterns
    if [[ ${#tracks[@]} -eq 0 ]]; then
        echo -e "${YELLOW}⚠️  Standard parsing failed, trying fallback...${NC}"
        # Try numbered list format (1. concept, 2. concept, etc.)
        while IFS= read -r line; do
            local trimmed=$(echo "$line" | sed 's/^[[:space:]]*//')
            if [[ "$trimmed" =~ ^[0-9]+[\.\)][[:space:]]* ]]; then
                local track_concept=$(echo "$trimmed" | sed 's/^[0-9]*[\.\)][[:space:]]*//')
                [[ -n "$track_concept" ]] && tracks+=("$track_concept")
            fi
        done <<< "$album_plan"
    fi

    if [[ ${#tracks[@]} -eq 0 ]]; then
        echo -e "${RED}❌ Failed to parse album tracks. Raw plan:${NC}"
        echo "$album_plan"
        exit 1
    fi

    echo ""
    echo -e "${GREEN}✅ Parsed ${#tracks[@]} tracks for album:${NC}"
    local i=1
    for t in "${tracks[@]}"; do
        echo -e "   ${CYAN}$i.${NC} $t"
        ((i++))
    done
    echo ""
    echo -e "${YELLOW}Starting generation (this will take a while)...${NC}"
    echo ""

    local track_num=1
    for concept in "${tracks[@]}"; do
        echo -e "${PURPLE}━━━ TRACK $track_num: $concept ━━━${NC}"
        generate_song "$artist" "$concept" "album-track-$track_num"
        ((track_num++))
        echo ""
    done

    echo -e "${PURPLE}💿 ALBUM COMPLETE!${NC}"
}

# VIBE MODE - Auto-pick artist
do_vibe() {
    local mood="$1"
    local concept="$2"

    echo -e "${PURPLE}🎯 VIBE MODE${NC}"
    echo -e "${BLUE}Mood: $mood${NC}"
    echo ""

    # Build artist summary
    local artist_list=""
    for f in "$ARTISTS_DIR"/*.md; do
        [[ -f "$f" ]] || continue
        local name=$(basename "$f" .md)
        local personality=$(grep "^personality:" "$f" | sed 's/personality: *//')
        local artist_mood=$(grep "^mood:" "$f" | sed 's/mood: *//')
        local energy=$(grep "^energy:" "$f" | sed 's/energy: *//')
        local genres=$(grep -A3 "^genres:" "$f" | grep "^  - " | sed 's/  - //' | tr '\n' ', ')
        artist_list="$artist_list
- $name: $personality | mood: $artist_mood | energy: $energy | genres: $genres"
    done

    echo -e "${CYAN}🤖 Matching vibe to artist...${NC}"

    local match=$(ollama_generate "Given this mood/vibe request: '$mood'

Available artists:
$artist_list

Which artist is the BEST match? Output ONLY the artist name (lowercase, no spaces). Just the name, nothing else.")

    # Clean the response
    local selected=$(echo "$match" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]' | head -1)

    echo -e "${GREEN}Selected: $selected${NC}"
    echo ""

    if [[ -f "$ARTISTS_DIR/$selected.md" ]]; then
        generate_song "$selected" "$concept" "vibe-match"
    else
        echo -e "${RED}❌ Could not match artist. Try: $match${NC}"
    fi
}

# REMIX MODE
do_remix() {
    local song_id="$1"
    local new_artist="$2"

    echo -e "${PURPLE}🔄 REMIX MODE${NC}"

    init_catalog

    # Find original song
    local original=$(python3 << EOF
import json
with open("$CATALOG_FILE", 'r') as f:
    catalog = json.load(f)
for song in catalog.get("songs", []):
    if str(song.get("id")) == "$song_id":
        print(f"LYRICS:{song.get('lyrics', '')}")
        print(f"CONCEPT:{song.get('concept', '')}")
        print(f"ORIGINAL:{song.get('artist', '')}")
        break
EOF
)

    local orig_lyrics=$(echo "$original" | grep "^LYRICS:" | sed 's/LYRICS://')
    local orig_concept=$(echo "$original" | grep "^CONCEPT:" | sed 's/CONCEPT://')
    local orig_artist=$(echo "$original" | grep "^ORIGINAL:" | sed 's/ORIGINAL://')

    if [[ -z "$orig_lyrics" ]]; then
        echo -e "${RED}❌ Song #$song_id not found${NC}"
        exit 1
    fi

    echo -e "${BLUE}Original: $orig_artist - $orig_concept${NC}"
    echo -e "${GREEN}Remixing with: $new_artist${NC}"
    echo ""

    local artist_file="$ARTISTS_DIR/$new_artist.md"
    [[ -f "$artist_file" ]] || { echo -e "${RED}❌ Artist not found${NC}"; exit 1; }

    local signature_tags=$(grep "^signature_tags:" "$artist_file" | sed 's/signature_tags: *//' | tr -d '"')
    local artist_name=$(grep "^name:" "$artist_file" | sed 's/name: *//')

    echo -e "${GREEN}⏳ Generating remix with ACE-Step...${NC}"

    local output=$("$ACESTEP_BIN" -t "$signature_tags" -l "$orig_lyrics" -d "$DURATION" -s "$STEPS" -f "$FORMAT" 2>&1)
    echo "$output"

    local audio_file=$(echo "$output" | grep "AUDIO_FILE=" | cut -d= -f2)
    if [[ -n "$audio_file" ]]; then
        add_to_catalog "$artist_name (remix)" "$orig_concept" "$orig_lyrics" "$audio_file" "$signature_tags" "remix-of-$song_id"
    fi
}

# REROLL MODE - Regenerate a song with new seed
do_reroll() {
    local song_id="$1"
    
    echo -e "${PURPLE}🎲 REROLL MODE${NC}"
    echo -e "${BLUE}Regenerating song #$song_id with new seed...${NC}"
    echo ""
    
    init_catalog
    
    # Find original song
    local original=$(python3 << EOF
import json
with open("$CATALOG_FILE", 'r') as f:
    catalog = json.load(f)
for song in catalog.get("songs", []):
    if str(song.get("id")) == "$song_id":
        print(f"LYRICS_START")
        print(song.get('lyrics', ''))
        print(f"LYRICS_END")
        print(f"CONCEPT:{song.get('concept', '')}")
        print(f"ARTIST:{song.get('artist', '')}")
        print(f"TAGS:{song.get('tags', '')}")
        print(f"SEED:{song.get('seed', 0)}")
        break
EOF
)

    # Parse multi-line lyrics
    local orig_lyrics=$(echo "$original" | sed -n '/LYRICS_START/,/LYRICS_END/p' | sed '1d;$d')
    local orig_concept=$(echo "$original" | grep "^CONCEPT:" | sed 's/CONCEPT://')
    local orig_artist=$(echo "$original" | grep "^ARTIST:" | sed 's/ARTIST://')
    local orig_tags=$(echo "$original" | grep "^TAGS:" | sed 's/TAGS://')
    local orig_seed=$(echo "$original" | grep "^SEED:" | sed 's/SEED://')

    if [[ -z "$orig_lyrics" ]] && [[ -z "$orig_concept" ]]; then
        echo -e "${RED}❌ Song #$song_id not found${NC}"
        exit 1
    fi

    echo -e "${CYAN}Original song:${NC}"
    echo -e "   Artist: $orig_artist"
    echo -e "   Concept: $orig_concept"
    echo -e "   Original seed: $orig_seed"
    echo ""
    
    # Generate new seed
    local new_seed=$(generate_seed)
    echo -e "${GREEN}🎲 New seed: $new_seed${NC}"
    echo ""
    
    echo -e "${GREEN}⏳ Regenerating with ACE-Step...${NC}"

    # Build acestep command with new seed
    local output=$("$ACESTEP_BIN" -t "$orig_tags" -l "$orig_lyrics" -d "$DURATION" -s "$STEPS" -f "$FORMAT" --scheduler "$SCHEDULER" --seed "$new_seed" 2>&1)
    echo "$output"

    local audio_file=$(echo "$output" | grep "AUDIO_FILE=" | cut -d= -f2)
    
    if [[ -n "$audio_file" ]] && [[ -f "$audio_file" ]]; then
        # Apply mastering if requested
        if [[ "$MASTER" == true ]]; then
            local mastered_file=$(master_audio "$audio_file")
            if [[ -n "$mastered_file" ]] && [[ -f "$mastered_file" ]]; then
                audio_file="$mastered_file"
            fi
        fi
        
        add_to_catalog "$orig_artist" "$orig_concept" "$orig_lyrics" "$audio_file" "$orig_tags" "reroll-of-$song_id" "$new_seed" "$QUALITY"
        echo -e "${GREEN}✅ Reroll complete: $audio_file${NC}"
    else
        echo -e "${RED}❌ Reroll failed${NC}"
    fi
}

# LYRICS FIRST MODE
do_lyrics_first() {
    local user_lyrics="$1"

    echo -e "${PURPLE}📝 LYRICS-FIRST MODE${NC}"
    echo ""

    # Build artist summary
    local artist_list=""
    for f in "$ARTISTS_DIR"/*.md; do
        [[ -f "$f" ]] || continue
        local name=$(basename "$f" .md)
        local personality=$(grep "^personality:" "$f" | sed 's/personality: *//')
        local mood=$(grep "^mood:" "$f" | sed 's/mood: *//')
        local genres=$(grep -A3 "^genres:" "$f" | grep "^  - " | sed 's/  - //' | tr '\n' ', ')
        local themes=$(grep -A5 "^themes:" "$f" | grep "^  - " | sed 's/  - //' | tr '\n' ', ')
        artist_list="$artist_list
- $name: $personality | mood: $mood | genres: $genres | themes: $themes"
    done

    echo -e "${CYAN}🤖 Analyzing lyrics and matching artist...${NC}"

    local match=$(ollama_generate "Analyze these lyrics and pick the BEST matching artist:

LYRICS:
$user_lyrics

AVAILABLE ARTISTS:
$artist_list

Which artist's style, mood, and themes best match these lyrics? Output ONLY the artist name (lowercase). Just the name.")

    local selected=$(echo "$match" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]' | head -1)

    echo -e "${GREEN}Best match: $selected${NC}"
    echo ""

    if [[ -f "$ARTISTS_DIR/$selected.md" ]]; then
        local artist_file="$ARTISTS_DIR/$selected.md"
        local signature_tags=$(grep "^signature_tags:" "$artist_file" | sed 's/signature_tags: *//' | tr -d '"')
        local artist_name=$(grep "^name:" "$artist_file" | sed 's/name: *//')

        echo -e "${PURPLE}🎤 Artist: $artist_name${NC}"
        echo -e "${YELLOW}🎵 Tags: $signature_tags${NC}"
        echo ""

        # Add structure tags if missing
        if [[ ! "$user_lyrics" == *"[verse]"* ]] && [[ ! "$user_lyrics" == *"[chorus]"* ]]; then
            echo -e "${CYAN}🤖 Adding structure tags to lyrics...${NC}"
            user_lyrics=$(ollama_generate "Add song structure tags ([verse], [chorus], [bridge], [outro]) to these lyrics. Keep the lyrics exactly the same, just add appropriate tags. Output ONLY the tagged lyrics:

$user_lyrics")
        fi

        echo -e "${GREEN}⏳ Generating with ACE-Step...${NC}"

        local output=$("$ACESTEP_BIN" -t "$signature_tags" -l "$user_lyrics" -d "$DURATION" -s "$STEPS" -f "$FORMAT" 2>&1)
        echo "$output"

        local audio_file=$(echo "$output" | grep "AUDIO_FILE=" | cut -d= -f2)
        if [[ -n "$audio_file" ]]; then
            init_catalog
            add_to_catalog "$artist_name" "lyrics-first" "$user_lyrics" "$audio_file" "$signature_tags" "lyrics-first"
        fi
    else
        echo -e "${RED}❌ Could not match artist${NC}"
    fi
}

# CREATE ARTIST
create_artist() {
    local description="$1"

    echo -e "${PURPLE}🎤 Creating new AI Artist...${NC}"
    echo -e "${CYAN}🤖 Using Ollama to design artist...${NC}"

    local profile=$(ollama_generate "Create a detailed AI music artist based on: \"$description\"

Output in this EXACT format:

---
name: ARTIST_NAME
real_name: Full Name
personality: One-line description
mood: 2-3 word mood
energy: low/medium/high
genres:
  - genre1
  - genre2
  - genre3
bpm_range: [min, max]
vocal_style: description
vocal_gender: male/female/none
instruments:
  - instrument1
  - instrument2
  - instrument3
themes:
  - theme1
  - theme2
  - theme3
  - theme4
signature_tags: \"full, comma, separated, acestep, tags, with, bpm, mood, vocals\"
---

# ARTIST_NAME

One paragraph bio.

## Vibe

2-3 sentences about sound.

## Lyric Style

- Bullet points about lyrics

## Best For

- Use case 1
- Use case 2

## Example Concepts

- \"concept 1\"
- \"concept 2\"

Output ONLY the formatted profile.")

    # Extract real_name (e.g., "John Smith") and convert to first-last format
    local real_name=$(echo "$profile" | grep "^real_name:" | head -1 | sed 's/real_name: *//')
    local stage_name=$(echo "$profile" | grep "^name:" | head -1 | sed 's/name: *//')
    
    # Use real_name for filename, fall back to stage name
    local name_for_file="${real_name:-$stage_name}"
    
    if [[ -z "$name_for_file" ]]; then
        echo -e "${RED}❌ Failed to generate artist (empty response from Ollama)${NC}"
        return 1
    fi
    
    # Convert to first-last format (lowercase, replace spaces with hyphens)
    local base_name=$(echo "$name_for_file" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd '[:alnum:]-')
    
    # Handle duplicates: first-last, first-last-2, first-last-3, etc.
    local artist_name="$base_name"
    local counter=2
    while [[ -f "$ARTISTS_DIR/$artist_name.md" ]]; do
        artist_name="${base_name}-${counter}"
        ((counter++))
    done

    echo "$profile" > "$ARTISTS_DIR/$artist_name.md"
    
    # Output for the API to parse
    echo "ARTIST_FILE=$ARTISTS_DIR/$artist_name.md"

    echo -e "${GREEN}✅ Created artist: $artist_name${NC}"
    echo -e "${BLUE}📁 File: $ARTISTS_DIR/$artist_name.md${NC}"
}

# CREATE GENRE
create_genre() {
    local description="$1"

    echo -e "${PURPLE}🎵 Creating new Genre Guide...${NC}"
    echo -e "${CYAN}🤖 Using Ollama to research genre...${NC}"

    local guide=$(ollama_generate "Create a music genre guide for: \"$description\"

Format:
# Genre Name - Genre Guide

## Characteristics
2-3 sentences.

## Recommended Tags
\`\`\`
tags, here, with, bpm
\`\`\`

### Tag Variations
| Subgenre | Tags |
|----------|------|
| Sub1 | tags |

## BPM Range
- Slow: XX-XX
- Mid: XX-XX
- Fast: XX-XX

## Song Structure
\`\`\`
[verse] - desc
[chorus] - desc
\`\`\`

## Lyric Style
- Themes: x, y, z
- Tone: description

### Writing Tips
1. Tip
2. Tip

## ACE-Step Notes
- Note about this genre

Output ONLY the guide.")

    local genre_name=$(echo "$guide" | grep "^# " | head -1 | sed 's/# //' | sed 's/ -.*//' | tr '[:upper:]' '[:lower:]' | tr ' ' '_' | tr -cd '[:alnum:]_')
    [[ -z "$genre_name" ]] && genre_name="genre_$(date +%s)"

    echo "$guide" > "$GENRES_DIR/$genre_name.md"

    echo -e "${GREEN}✅ Created genre: $genre_name${NC}"
    echo -e "${BLUE}📁 File: $GENRES_DIR/$genre_name.md${NC}"
}

# ============ GENRE FUSION ============
do_fusion() {
    local genre1="$1"
    local genre2="$2"
    local concept="$3"
    
    echo -e "${PURPLE}🔀 GENRE FUSION MODE${NC}"
    echo -e "${GREEN}$genre1${NC} + ${GREEN}$genre2${NC}"
    echo -e "${BLUE}Concept: $concept${NC}"
    echo ""
    
    echo -e "${CYAN}🤖 Creating fusion artist with Ollama...${NC}"
    
    # Get genre guides if they exist
    local genre1_guide=""
    local genre2_guide=""
    for f in "$GENRES_DIR"/*.md; do
        [[ -f "$f" ]] || continue
        local name=$(basename "$f" .md | tr '[:upper:]' '[:lower:]')
        [[ "$name" == *"$genre1"* ]] && genre1_guide=$(cat "$f")
        [[ "$name" == *"$genre2"* ]] && genre2_guide=$(cat "$f")
    done
    
    local fusion_prompt="Create a fusion music style combining $genre1 and $genre2.

Genre 1 Reference:
$genre1_guide

Genre 2 Reference:
$genre2_guide

Output ONLY a comma-separated list of ACE-Step tags that blend both genres. Include:
- Blended genre descriptors
- Instruments from both genres
- A BPM that works for both
- Mood descriptors
- Vocal style if applicable

Example format: genre fusion, instrument1, instrument2, XXX bpm, mood1, mood2, vocal style

Output ONLY the tags, nothing else."

    local fusion_tags=$(ollama_generate "$fusion_prompt" | head -1 | tr -d '\n')
    
    echo -e "${YELLOW}🎵 Fusion Tags: $fusion_tags${NC}"
    echo ""
    
    # Generate lyrics
    local lyrics_prompt="Write lyrics for a $genre1 + $genre2 fusion song about: $concept

The song should blend elements of both genres in its lyrical style.
Use structure tags: [verse], [chorus], [bridge]
Keep it 2 verses, 2 choruses, 1 bridge.

Output ONLY the lyrics with tags."

    echo -e "${CYAN}🤖 Generating fusion lyrics...${NC}"
    local lyrics=$(ollama_generate "$lyrics_prompt")
    
    echo ""
    echo -e "${PURPLE}📝 Fusion Lyrics:${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "$lyrics"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    echo -e "${GREEN}⏳ Generating fusion track...${NC}"
    
    local seed=$(generate_seed)
    local output=$("$ACESTEP_BIN" -t "$fusion_tags" -l "$lyrics" -d "$DURATION" -s "$STEPS" -f "$FORMAT" --scheduler "$SCHEDULER" --seed "$seed" 2>&1)
    echo "$output"
    
    local audio_file=$(echo "$output" | grep "AUDIO_FILE=" | cut -d= -f2)
    
    if [[ -n "$audio_file" ]] && [[ -f "$audio_file" ]]; then
        [[ "$MASTER" == true ]] && audio_file=$(master_audio "$audio_file")
        init_catalog
        add_to_catalog "Fusion ($genre1 x $genre2)" "$concept" "$lyrics" "$audio_file" "$fusion_tags" "fusion" "$seed" "$QUALITY"
        echo -e "${GREEN}✅ Fusion complete: $audio_file${NC}"
        update_stats "fusion" "success"
    else
        echo -e "${RED}❌ Fusion generation failed${NC}"
        update_stats "fusion" "fail"
    fi
}

# ============ SOUND-ALIKE ============
do_like() {
    local real_artist="$1"
    local concept="$2"
    
    echo -e "${PURPLE}🎭 SOUND-ALIKE MODE${NC}"
    echo -e "${GREEN}Style of: $real_artist${NC}"
    echo -e "${BLUE}Concept: $concept${NC}"
    echo ""
    
    echo -e "${CYAN}🤖 Analyzing artist style with Ollama...${NC}"
    
    local style_prompt="Analyze the musical style of $real_artist and create ACE-Step tags to recreate their sound.

Consider:
- Their primary genre(s)
- Typical instruments and production style
- Vocal characteristics (if applicable)
- Typical BPM range
- Mood and energy
- Era/decade influences

Output ONLY a comma-separated list of ACE-Step tags. Format:
genre, subgenre, instruments, BPM, mood, vocal style

Be specific and detailed. Output ONLY the tags, no explanations."

    local style_tags=$(ollama_generate "$style_prompt" | head -1 | tr -d '\n')
    
    echo -e "${YELLOW}🎵 Style Tags: $style_tags${NC}"
    echo ""
    
    # Generate lyrics in their style
    local lyrics_prompt="Write song lyrics in the style of $real_artist about: $concept

Capture their:
- Lyrical themes and vocabulary
- Songwriting structure
- Emotional tone
- Any signature phrases or techniques

Use structure tags: [verse], [chorus], [bridge]
Output ONLY the lyrics with tags."

    echo -e "${CYAN}🤖 Generating lyrics in $real_artist's style...${NC}"
    local lyrics=$(ollama_generate "$lyrics_prompt")
    
    echo ""
    echo -e "${PURPLE}📝 Lyrics:${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "$lyrics"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    echo -e "${GREEN}⏳ Generating sound-alike track...${NC}"
    
    local seed=$(generate_seed)
    local output=$("$ACESTEP_BIN" -t "$style_tags" -l "$lyrics" -d "$DURATION" -s "$STEPS" -f "$FORMAT" --scheduler "$SCHEDULER" --seed "$seed" 2>&1)
    echo "$output"
    
    local audio_file=$(echo "$output" | grep "AUDIO_FILE=" | cut -d= -f2)
    
    if [[ -n "$audio_file" ]] && [[ -f "$audio_file" ]]; then
        [[ "$MASTER" == true ]] && audio_file=$(master_audio "$audio_file")
        init_catalog
        add_to_catalog "Like $real_artist" "$concept" "$lyrics" "$audio_file" "$style_tags" "sound-alike" "$seed" "$QUALITY"
        echo -e "${GREEN}✅ Sound-alike complete: $audio_file${NC}"
        update_stats "sound-alike" "success"
    else
        echo -e "${RED}❌ Sound-alike generation failed${NC}"
        update_stats "sound-alike" "fail"
    fi
}

# ============ RATING SYSTEM ============
rate_song() {
    local song_id="$1"
    local rating="$2"
    
    if [[ ! "$rating" =~ ^[1-5]$ ]]; then
        echo -e "${RED}❌ Rating must be 1-5${NC}"
        exit 1
    fi
    
    init_catalog
    
    python3 << EOF
import json

with open("$CATALOG_FILE", 'r') as f:
    catalog = json.load(f)

found = False
for song in catalog.get("songs", []):
    if str(song.get("id")) == "$song_id":
        song["rating"] = $rating
        found = True
        print(f"\033[0;32m✅ Rated song #{song['id']} with {'⭐' * $rating}\033[0m")
        print(f"   {song.get('artist', 'Unknown')} - {song.get('concept', '')[:50]}...")
        break

if not found:
    print(f"\033[0;31m❌ Song #{$song_id} not found\033[0m")
else:
    with open("$CATALOG_FILE", 'w') as f:
        json.dump(catalog, f, indent=2)
EOF
}

show_top_rated() {
    init_catalog
    
    echo -e "${PURPLE}⭐ TOP RATED SONGS${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    python3 << EOF
import json

with open("$CATALOG_FILE", 'r') as f:
    catalog = json.load(f)

songs = [s for s in catalog.get("songs", []) if s.get("rating")]
songs.sort(key=lambda x: (-x.get("rating", 0), x.get("date", "")))

if not songs:
    print("No rated songs yet. Use --rate <song_id> <1-5> to rate songs.")
else:
    for song in songs[:20]:
        stars = "⭐" * song.get("rating", 0)
        print(f"{stars} \033[0;32m#{song['id']}\033[0m | \033[0;34m{song['artist']}\033[0m")
        print(f"   {song.get('concept', '')[:50]}...")
        print(f"   📁 {song.get('file', 'N/A')}")
        print()
EOF
}

# ============ STATISTICS ============
init_stats() {
    if [[ ! -f "$STATS_FILE" ]]; then
        echo '{"generations": [], "by_artist": {}, "by_mode": {}, "by_quality": {}}' > "$STATS_FILE"
    fi
}

update_stats() {
    local mode="$1"
    local result="$2"  # success or fail
    
    init_stats
    
    python3 << EOF
import json
from datetime import datetime

with open("$STATS_FILE", 'r') as f:
    stats = json.load(f)

# Add generation record
stats["generations"].append({
    "timestamp": datetime.now().isoformat(),
    "mode": "$mode",
    "result": "$result",
    "quality": "$QUALITY",
    "artist": "$ARTIST" if "$ARTIST" else "N/A"
})

# Update by_mode
if "$mode" not in stats["by_mode"]:
    stats["by_mode"]["$mode"] = {"success": 0, "fail": 0}
stats["by_mode"]["$mode"]["$result"] += 1

# Update by_quality
if "$QUALITY" not in stats["by_quality"]:
    stats["by_quality"]["$QUALITY"] = {"success": 0, "fail": 0}
stats["by_quality"]["$QUALITY"]["$result"] += 1

# Update by_artist if applicable
if "$ARTIST":
    if "$ARTIST" not in stats["by_artist"]:
        stats["by_artist"]["$ARTIST"] = {"success": 0, "fail": 0}
    stats["by_artist"]["$ARTIST"]["$result"] += 1

# Keep only last 1000 generations
stats["generations"] = stats["generations"][-1000:]

with open("$STATS_FILE", 'w') as f:
    json.dump(stats, f, indent=2)
EOF
}

show_stats() {
    local filter_artist="$1"
    
    init_stats
    
    echo -e "${PURPLE}📊 GENERATION STATISTICS${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    python3 << EOF
import json

with open("$STATS_FILE", 'r') as f:
    stats = json.load(f)

total = len(stats.get("generations", []))
success = sum(1 for g in stats.get("generations", []) if g.get("result") == "success")
fail = total - success
rate = (success / total * 100) if total > 0 else 0

print(f"\033[0;36mTotal Generations:\033[0m {total}")
print(f"\033[0;32mSuccessful:\033[0m {success} ({rate:.1f}%)")
print(f"\033[0;31mFailed:\033[0m {fail}")
print()

filter_artist = "$filter_artist".lower() if "$filter_artist" else None

if filter_artist:
    print(f"\033[0;35m📈 Stats for artist: {filter_artist}\033[0m")
    for artist, data in stats.get("by_artist", {}).items():
        if filter_artist in artist.lower():
            total_a = data["success"] + data["fail"]
            rate_a = (data["success"] / total_a * 100) if total_a > 0 else 0
            print(f"   {artist}: {data['success']}/{total_a} ({rate_a:.1f}% success)")
else:
    print("\033[0;35m📈 By Mode:\033[0m")
    for mode, data in stats.get("by_mode", {}).items():
        total_m = data["success"] + data["fail"]
        rate_m = (data["success"] / total_m * 100) if total_m > 0 else 0
        print(f"   {mode}: {data['success']}/{total_m} ({rate_m:.1f}% success)")
    
    print()
    print("\033[0;35m📈 By Quality:\033[0m")
    for quality, data in stats.get("by_quality", {}).items():
        total_q = data["success"] + data["fail"]
        rate_q = (data["success"] / total_q * 100) if total_q > 0 else 0
        print(f"   {quality}: {data['success']}/{total_q} ({rate_q:.1f}% success)")
    
    print()
    print("\033[0;35m📈 Top Artists:\033[0m")
    artists = sorted(stats.get("by_artist", {}).items(), 
                     key=lambda x: x[1]["success"], reverse=True)[:10]
    for artist, data in artists:
        print(f"   {artist}: {data['success']} successful")
EOF
}

# ============ QUEUE SYSTEM ============
init_queue() {
    if [[ ! -f "$QUEUE_FILE" ]]; then
        echo '{"queue": []}' > "$QUEUE_FILE"
    fi
}

queue_add() {
    local artist="$1"
    local concept="$2"
    
    init_queue
    
    python3 << EOF
import json
from datetime import datetime

with open("$QUEUE_FILE", 'r') as f:
    queue_data = json.load(f)

item = {
    "id": int(datetime.now().timestamp() * 1000),
    "artist": "$artist",
    "concept": """$concept""",
    "quality": "$QUALITY",
    "takes": $TAKES,
    "master": $( [[ "$MASTER" == true ]] && echo "True" || echo "False" ),
    "added": datetime.now().isoformat()
}

queue_data["queue"].append(item)

with open("$QUEUE_FILE", 'w') as f:
    json.dump(queue_data, f, indent=2)

print(f"\033[0;32m✅ Added to queue: {item['artist']} - {item['concept'][:40]}...\033[0m")
print(f"   Queue size: {len(queue_data['queue'])} items")
EOF
}

queue_list() {
    init_queue
    
    echo -e "${PURPLE}📋 GENERATION QUEUE${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    python3 << EOF
import json

with open("$QUEUE_FILE", 'r') as f:
    queue_data = json.load(f)

queue = queue_data.get("queue", [])
if not queue:
    print("Queue is empty.")
else:
    for i, item in enumerate(queue, 1):
        print(f"\033[0;36m{i}.\033[0m \033[0;34m{item['artist']}\033[0m - {item['concept'][:40]}...")
        print(f"   Quality: {item.get('quality', 'normal')} | Takes: {item.get('takes', 1)} | Master: {item.get('master', False)}")
        print()
    print(f"Total: {len(queue)} items in queue")
EOF
}

queue_clear() {
    echo '{"queue": []}' > "$QUEUE_FILE"
    echo -e "${GREEN}✅ Queue cleared${NC}"
}

queue_run() {
    init_queue
    
    echo -e "${PURPLE}🚀 RUNNING QUEUE${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Read queue into bash
    local queue_json=$(cat "$QUEUE_FILE")
    local count=$(echo "$queue_json" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('queue', [])))")
    
    if [[ "$count" -eq 0 ]]; then
        echo -e "${YELLOW}Queue is empty${NC}"
        return
    fi
    
    echo -e "${GREEN}Processing $count items...${NC}"
    echo ""
    
    local processed=0
    while true; do
        # Get first item
        local item=$(python3 << EOF
import json
with open("$QUEUE_FILE", 'r') as f:
    queue_data = json.load(f)
queue = queue_data.get("queue", [])
if queue:
    item = queue[0]
    print(f"ARTIST:{item['artist']}")
    print(f"CONCEPT:{item['concept']}")
    print(f"QUALITY:{item.get('quality', 'normal')}")
    print(f"TAKES:{item.get('takes', 1)}")
    print(f"MASTER:{item.get('master', False)}")
EOF
)
        
        [[ -z "$item" ]] && break
        
        local q_artist=$(echo "$item" | grep "^ARTIST:" | sed 's/ARTIST://')
        local q_concept=$(echo "$item" | grep "^CONCEPT:" | sed 's/CONCEPT://')
        local q_quality=$(echo "$item" | grep "^QUALITY:" | sed 's/QUALITY://')
        local q_takes=$(echo "$item" | grep "^TAKES:" | sed 's/TAKES://')
        local q_master=$(echo "$item" | grep "^MASTER:" | sed 's/MASTER://')
        
        [[ -z "$q_artist" ]] && break
        
        ((processed++))
        echo -e "${PURPLE}━━━ QUEUE ITEM $processed/$count ━━━${NC}"
        
        # Set options from queue item
        QUALITY="$q_quality"
        apply_quality_preset "$QUALITY"
        TAKES="$q_takes"
        [[ "$q_master" == "True" ]] && MASTER=true || MASTER=false
        
        # Generate
        generate_song "$q_artist" "$q_concept" "queue"
        
        # Remove from queue
        python3 << EOF
import json
with open("$QUEUE_FILE", 'r') as f:
    queue_data = json.load(f)
queue_data["queue"] = queue_data.get("queue", [])[1:]
with open("$QUEUE_FILE", 'w') as f:
    json.dump(queue_data, f, indent=2)
EOF
        
        echo ""
    done
    
    echo -e "${GREEN}✅ Queue complete! Processed $processed items${NC}"
}

# ============ TEMPLATE SYSTEM ============
init_templates() {
    mkdir -p "$TEMPLATES_DIR"
}

template_save() {
    local name="$1"
    
    init_templates
    
    local template_file="$TEMPLATES_DIR/$name.json"
    
    python3 << EOF
import json

template = {
    "name": "$name",
    "quality": "$QUALITY",
    "steps": $STEPS,
    "scheduler": "$SCHEDULER",
    "format": "$FORMAT",
    "duration": $DURATION,
    "takes": $TAKES,
    "master": $( [[ "$MASTER" == true ]] && echo "True" || echo "False" )
}

with open("$template_file", 'w') as f:
    json.dump(template, f, indent=2)

print(f"\033[0;32m✅ Saved template: $name\033[0m")
print(f"   Quality: {template['quality']}")
print(f"   Steps: {template['steps']}")
print(f"   Scheduler: {template['scheduler']}")
print(f"   Format: {template['format']}")
print(f"   Duration: {template['duration']}s")
print(f"   Takes: {template['takes']}")
print(f"   Master: {template['master']}")
EOF
}

template_load() {
    local name="$1"
    local template_file="$TEMPLATES_DIR/$name.json"
    
    if [[ ! -f "$template_file" ]]; then
        echo -e "${RED}❌ Template '$name' not found${NC}"
        exit 1
    fi
    
    # Source template values
    eval $(python3 << EOF
import json
with open("$template_file", 'r') as f:
    t = json.load(f)
print(f"QUALITY={t.get('quality', 'normal')}")
print(f"STEPS={t.get('steps', 60)}")
print(f"SCHEDULER={t.get('scheduler', 'euler')}")
print(f"FORMAT={t.get('format', 'mp3')}")
print(f"DURATION={t.get('duration', 120)}")
print(f"TAKES={t.get('takes', 1)}")
print(f"MASTER={'true' if t.get('master') else 'false'}")
EOF
)
    
    echo -e "${GREEN}✅ Loaded template: $name${NC}"
}

template_list() {
    init_templates
    
    echo -e "${PURPLE}📑 SAVED TEMPLATES${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    local found=false
    for f in "$TEMPLATES_DIR"/*.json; do
        [[ -f "$f" ]] || continue
        found=true
        local name=$(basename "$f" .json)
        local quality=$(python3 -c "import json; print(json.load(open('$f')).get('quality', 'normal'))")
        local takes=$(python3 -c "import json; print(json.load(open('$f')).get('takes', 1))")
        local master=$(python3 -c "import json; print('Yes' if json.load(open('$f')).get('master') else 'No')")
        echo -e "${GREEN}$name${NC} — Quality: $quality | Takes: $takes | Master: $master"
    done
    
    [[ "$found" == false ]] && echo "No templates saved yet."
}

template_show() {
    local name="$1"
    local template_file="$TEMPLATES_DIR/$name.json"
    
    if [[ ! -f "$template_file" ]]; then
        echo -e "${RED}❌ Template '$name' not found${NC}"
        exit 1
    fi
    
    echo -e "${PURPLE}📑 Template: $name${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    python3 -c "import json; t=json.load(open('$template_file')); [print(f'  {k}: {v}') for k,v in t.items()]"
}

# ============ MAIN ============

ACTION=""
ARTIST=""
ARTIST2=""
CONCEPT=""
CATALOG_FILTER_ARTIST=""
CATALOG_SEARCH=""
CATALOG_TOP=false
SONG_ID=""
USER_LYRICS=""
MANUAL_SEED=""
STEPS_OVERRIDE=""
RATING=""
QUEUE_ACTION=""
TEMPLATE_ACTION=""
TEMPLATE_NAME=""
GENRE1=""
GENRE2=""
LIKE_ARTIST=""
STATS_ARTIST=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --list) ACTION="list"; shift ;;
        --show) ACTION="show"; ARTIST="$2"; shift 2 ;;
        --artist) ACTION="create_artist"; CONCEPT="$2"; shift 2 ;;
        --genre) ACTION="create_genre"; CONCEPT="$2"; shift 2 ;;
        --collab) ACTION="collab"; ARTIST="$2"; ARTIST2="$3"; CONCEPT="$4"; shift 4 ;;
        --battle) ACTION="battle"; ARTIST="$2"; ARTIST2="$3"; CONCEPT="$4"; shift 4 ;;
        --album) ACTION="album"; ARTIST="$2"; CONCEPT="$3"; shift 3 ;;
        --vibe) ACTION="vibe"; CONCEPT="$2"; USER_LYRICS="$3"; shift 3 ;;
        --remix) ACTION="remix"; SONG_ID="$2"; ARTIST="$3"; shift 3 ;;
        --reroll) ACTION="reroll"; SONG_ID="$2"; shift 2 ;;
        --lyrics) ACTION="lyrics_first"; USER_LYRICS="$2"; shift 2 ;;
        # New modes
        --fusion) ACTION="fusion"; GENRE1="$2"; GENRE2="$3"; CONCEPT="$4"; shift 4 ;;
        --like) ACTION="like"; LIKE_ARTIST="$2"; CONCEPT="$3"; shift 3 ;;
        --rate) ACTION="rate"; SONG_ID="$2"; RATING="$3"; shift 3 ;;
        --stats) ACTION="stats"; shift ;;
        --queue)
            ACTION="queue"
            QUEUE_ACTION="$2"
            shift 2
            # Handle queue add specially
            if [[ "$QUEUE_ACTION" == "add" ]]; then
                ARTIST="$1"; shift
                CONCEPT="$1"; shift
            fi
            ;;
        --template)
            ACTION="template"
            TEMPLATE_ACTION="$2"
            shift 2
            if [[ "$TEMPLATE_ACTION" == "save" ]] || [[ "$TEMPLATE_ACTION" == "load" ]] || [[ "$TEMPLATE_ACTION" == "show" ]]; then
                TEMPLATE_NAME="$1"; shift
            fi
            ;;
        # Catalog options
        --catalog) ACTION="catalog"; shift ;;
        --search) CATALOG_SEARCH="$2"; shift 2 ;;
        --top) CATALOG_TOP=true; shift ;;
        # Production options
        --quality) QUALITY="$2"; shift 2 ;;
        --takes) TAKES="$2"; shift 2 ;;
        --master) MASTER=true; shift ;;
        --scheduler) SCHEDULER="$2"; shift 2 ;;
        --seed) MANUAL_SEED="$2"; shift 2 ;;
        # Legacy options
        --duration) DURATION="$2"; shift 2 ;;
        --steps) STEPS_OVERRIDE="$2"; shift 2 ;;
        --model) OLLAMA_MODEL="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *)
            if [[ "$ACTION" == "catalog" ]]; then
                if [[ "$1" == "--artist" ]]; then
                    CATALOG_FILTER_ARTIST="$2"; shift 2
                else
                    shift
                fi
            elif [[ "$ACTION" == "stats" ]]; then
                if [[ "$1" == "--artist" ]]; then
                    STATS_ARTIST="$2"; shift 2
                else
                    shift
                fi
            elif [[ -z "$ARTIST" ]]; then
                ARTIST="$1"; shift
            elif [[ -z "$CONCEPT" ]]; then
                CONCEPT="$1"; shift
            else
                shift
            fi
            ;;
    esac
done

# Apply quality preset (sets STEPS, SCHEDULER, FORMAT) - skip for some actions
if [[ "$ACTION" != "template" ]] || [[ "$TEMPLATE_ACTION" != "load" ]]; then
    apply_quality_preset "$QUALITY"
fi

# Allow manual override of steps after preset
[[ -n "$STEPS_OVERRIDE" ]] && STEPS="$STEPS_OVERRIDE"

# Show production settings if non-default (for generation actions)
if [[ "$ACTION" == "" ]] || [[ "$ACTION" == "collab" ]] || [[ "$ACTION" == "album" ]] || [[ "$ACTION" == "fusion" ]] || [[ "$ACTION" == "like" ]]; then
    if [[ "$TAKES" -gt 1 ]] || [[ "$MASTER" == true ]] || [[ "$QUALITY" != "normal" ]]; then
        echo -e "${PURPLE}━━━ PRODUCTION SETTINGS ━━━${NC}"
        echo -e "${CYAN}Quality:${NC} $QUALITY (steps=$STEPS, scheduler=$SCHEDULER)"
        echo -e "${CYAN}Takes:${NC} $TAKES"
        echo -e "${CYAN}Mastering:${NC} $MASTER"
        [[ -n "$MANUAL_SEED" ]] && echo -e "${CYAN}Seed:${NC} $MANUAL_SEED"
        echo ""
    fi
fi

case $ACTION in
    list) list_artists ;;
    show) show_artist "$ARTIST" ;;
    catalog)
        if [[ "$CATALOG_TOP" == true ]]; then
            show_top_rated
        else
            show_catalog "$CATALOG_FILTER_ARTIST" "$CATALOG_SEARCH"
        fi
        ;;
    create_artist) create_artist "$CONCEPT" ;;
    create_genre) create_genre "$CONCEPT" ;;
    collab) do_collab "$ARTIST" "$ARTIST2" "$CONCEPT" ;;
    battle) do_battle "$ARTIST" "$ARTIST2" "$CONCEPT" ;;
    album) do_album "$ARTIST" "$CONCEPT" ;;
    vibe) do_vibe "$CONCEPT" "$USER_LYRICS" ;;
    remix) do_remix "$SONG_ID" "$ARTIST" ;;
    reroll) do_reroll "$SONG_ID" ;;
    lyrics_first) do_lyrics_first "$USER_LYRICS" ;;
    fusion) do_fusion "$GENRE1" "$GENRE2" "$CONCEPT" ;;
    like) do_like "$LIKE_ARTIST" "$CONCEPT" ;;
    rate) rate_song "$SONG_ID" "$RATING" ;;
    stats) show_stats "$STATS_ARTIST" ;;
    queue)
        case $QUEUE_ACTION in
            add) queue_add "$ARTIST" "$CONCEPT" ;;
            list) queue_list ;;
            run) queue_run ;;
            clear) queue_clear ;;
            *) echo -e "${RED}❌ Unknown queue action: $QUEUE_ACTION${NC}"; echo "Use: add, list, run, clear" ;;
        esac
        ;;
    template)
        case $TEMPLATE_ACTION in
            save) template_save "$TEMPLATE_NAME" ;;
            load) template_load "$TEMPLATE_NAME"; echo "Template loaded. Now run a generation command." ;;
            list) template_list ;;
            show) template_show "$TEMPLATE_NAME" ;;
            *) echo -e "${RED}❌ Unknown template action: $TEMPLATE_ACTION${NC}"; echo "Use: save, load, list, show" ;;
        esac
        ;;
    *)
        if [[ -z "$ARTIST" ]]; then
            usage; exit 1
        fi
        if [[ -z "$CONCEPT" ]]; then
            echo -e "${RED}❌ Please provide a song concept${NC}"
            exit 1
        fi
        generate_song "$ARTIST" "$CONCEPT"
        update_stats "standard" "success"
        ;;
esac
