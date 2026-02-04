#!/usr/bin/env python3
"""
Music Planner Dashboard - Web UI for AI Music Generation
"""

import os
import json
import subprocess
import glob
import re
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_from_directory
import yaml

app = Flask(__name__)

# Paths
BASE_DIR = Path(__file__).parent.parent
ARTISTS_DIR = BASE_DIR / "artists"
CATALOG_DIR = BASE_DIR / "catalog"
CATALOG_FILE = CATALOG_DIR / "songs.json"
GENRES_DIR = BASE_DIR.parent / "ACESTEP_genres"
MUSIC_DIR = Path.home() / "Music" / "acestep"
GENERATE_SCRIPT = BASE_DIR / "generate.sh"

def parse_artist_file(filepath):
    """Parse artist markdown file with YAML frontmatter."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Extract YAML frontmatter
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1])
                body = parts[2].strip()
                frontmatter['body'] = body
                frontmatter['filename'] = filepath.stem
                return frontmatter
            except:
                pass
    
    return {'filename': filepath.stem, 'name': filepath.stem, 'body': content}

def get_artists():
    """Get all artists."""
    artists = []
    for f in ARTISTS_DIR.glob("*.md"):
        artist = parse_artist_file(f)
        artists.append(artist)
    return sorted(artists, key=lambda x: x.get('name', '').lower())

def get_genres():
    """Get all genre guides."""
    genres = []
    for f in GENRES_DIR.glob("*.md"):
        with open(f, 'r') as file:
            content = file.read()
        
        # Extract title from first heading
        title_match = re.search(r'^# (.+)', content, re.MULTILINE)
        title = title_match.group(1) if title_match else f.stem
        
        # Extract recommended tags
        tags_match = re.search(r'```\n([^`]+)\n```', content)
        tags = tags_match.group(1).strip() if tags_match else ""
        
        genres.append({
            'filename': f.stem,
            'title': title,
            'tags': tags,
            'content': content
        })
    return sorted(genres, key=lambda x: x['title'].lower())

def get_catalog():
    """Get song catalog."""
    if not CATALOG_FILE.exists():
        return []
    with open(CATALOG_FILE, 'r') as f:
        data = json.load(f)
    return data.get('songs', [])

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/songs')
def songs_page():
    return render_template('songs.html')

@app.route('/artists')
def artists_page():
    return render_template('artists.html')

@app.route('/genres')
def genres_page():
    return render_template('genres.html')

@app.route('/generate')
def generate_page():
    return render_template('generate.html')

@app.route('/create')
def create_page():
    return render_template('create.html')

# API Routes
@app.route('/api/stats')
def api_stats():
    return jsonify({
        'artists': len(get_artists()),
        'songs': len(get_catalog()),
        'genres': len(get_genres())
    })

@app.route('/api/artists')
def api_artists():
    return jsonify(get_artists())

@app.route('/api/artists/<name>')
def api_artist(name):
    filepath = ARTISTS_DIR / f"{name}.md"
    if filepath.exists():
        return jsonify(parse_artist_file(filepath))
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/genres')
def api_genres():
    return jsonify(get_genres())

@app.route('/api/songs')
def api_songs():
    songs = get_catalog()
    # Add file existence check
    for song in songs:
        song['file_exists'] = Path(song.get('file', '')).exists()
    return jsonify(songs[::-1])  # Newest first

@app.route('/api/audio/<path:filename>')
def api_audio(filename):
    """Serve audio files."""
    return send_from_directory(MUSIC_DIR, filename)

@app.route('/api/generate', methods=['POST'])
def api_generate():
    """Generate a song."""
    data = request.json
    mode = data.get('mode', 'standard')
    artist = data.get('artist')
    artist2 = data.get('artist2')
    concept = data.get('concept')
    lyrics = data.get('lyrics')
    vibe = data.get('vibe')
    duration = data.get('duration', 120)
    steps = data.get('steps', 60)
    
    # Build command
    cmd = [str(GENERATE_SCRIPT)]
    
    if mode == 'standard':
        cmd.extend([artist, concept])
    elif mode == 'collab':
        cmd.extend(['--collab', artist, artist2, concept])
    elif mode == 'battle':
        cmd.extend(['--battle', artist, artist2, concept])
    elif mode == 'album':
        cmd.extend(['--album', artist, concept])
    elif mode == 'vibe':
        cmd.extend(['--vibe', vibe, concept])
    elif mode == 'lyrics':
        cmd.extend(['--lyrics', lyrics])
    
    cmd.extend(['--duration', str(duration), '--steps', str(steps)])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(BASE_DIR)
        )
        
        # Extract audio file from output
        audio_match = re.search(r'AUDIO_FILE=(.+)', result.stdout)
        audio_file = audio_match.group(1) if audio_match else None
        
        return jsonify({
            'success': result.returncode == 0,
            'output': result.stdout,
            'error': result.stderr,
            'audio_file': audio_file
        })
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Generation timed out'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/artist', methods=['POST'])
def api_create_artist():
    """Create a new artist."""
    data = request.json
    description = data.get('description')
    
    cmd = [str(GENERATE_SCRIPT), '--artist', description]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(BASE_DIR)
        )
        return jsonify({
            'success': result.returncode == 0,
            'output': result.stdout,
            'error': result.stderr
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/genre', methods=['POST'])
def api_create_genre():
    """Create a new genre."""
    data = request.json
    description = data.get('description')
    
    cmd = [str(GENERATE_SCRIPT), '--genre', description]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(BASE_DIR)
        )
        return jsonify({
            'success': result.returncode == 0,
            'output': result.stdout,
            'error': result.stderr
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # Ensure directories exist
    CATALOG_DIR.mkdir(exist_ok=True)
    if not CATALOG_FILE.exists():
        with open(CATALOG_FILE, 'w') as f:
            json.dump({'songs': []}, f)
    
    print("🎵 Music Planner Dashboard")
    print("   http://localhost:5555")
    app.run(host='0.0.0.0', port=5555, debug=True)
