#!/usr/bin/env python3
"""
Artist Photo Generator for Music Planner

Generates profile photos for AI artists using ComfyUI.
"""

import sys
import json
from pathlib import Path

# Add comfyui-portraits to path
PORTRAITS_DIR = Path(__file__).parent.parent / "comfyui-portraits"
sys.path.insert(0, str(PORTRAITS_DIR))

from generate import generate, GENDERS, AGES, ETHNICITIES, STYLES

# Artist visual profiles
ARTIST_PROFILES = {
    "nova": {
        "gender": "female",
        "age": "20s", 
        "style": "editorial fashion",
        "lighting": "neon lights",
        "clothing": "elegant evening wear",
        "additional": "dreamy ethereal look, soft features"
    },
    "blade": {
        "gender": "male",
        "age": "20s",
        "style": "artistic portrait",
        "lighting": "dramatic side lighting",
        "clothing": "streetwear",
        "additional": "intense gaze, urban aesthetic, tattoos"
    },
    "velvet": {
        "gender": "female",
        "age": "30s",
        "style": "glamour",
        "lighting": "warm interior lighting",
        "clothing": "elegant evening wear",
        "additional": "sultry expression, luxurious setting"
    },
    "rust": {
        "gender": "male",
        "age": "40s",
        "style": "documentary",
        "lighting": "golden hour sunlight",
        "clothing": "casual t-shirt and jeans",
        "additional": "weathered face, rugged outdoorsy look, beard"
    },
    "phoenix": {
        "gender": "female",
        "age": "30s",
        "style": "editorial fashion",
        "lighting": "dramatic side lighting",
        "clothing": "athletic wear",
        "additional": "powerful confident pose, strong features"
    },
    "ghost": {
        "gender": "male",
        "age": "20s",
        "style": "artistic portrait",
        "lighting": "neon lights",
        "clothing": "streetwear",
        "additional": "mysterious shadowy, hood, dark aesthetic"
    },
    "zephyr": {
        "gender": "male",
        "age": "30s",
        "style": "cinematic",
        "lighting": "neon lights",
        "clothing": "smart casual",
        "additional": "synthwave aesthetic, 80s retro vibe, sunglasses at night"
    }
}


def generate_artist_photo(
    artist: str,
    framing: str = "headshot",
    quality: str = "high",
    resolution: str = "hd",
    aspect: str = "square",
    seed: int = None
) -> Path:
    """Generate a photo for a music planner artist."""
    
    artist = artist.lower()
    profile = ARTIST_PROFILES.get(artist)
    
    if not profile:
        print(f"⚠️ Unknown artist '{artist}', using random profile")
        profile = {
            "gender": None,
            "age": None,
            "style": "photorealistic"
        }
    
    print(f"🎤 Generating photo for {artist.upper()}...")
    
    return generate(
        gender=profile.get("gender"),
        age=profile.get("age"),
        ethnicity=profile.get("ethnicity"),
        clothing=profile.get("clothing"),
        framing=framing,
        lighting=profile.get("lighting"),
        location=profile.get("location"),
        style=profile.get("style", "photorealistic"),
        additional=profile.get("additional"),
        quality=quality,
        resolution=resolution,
        aspect=aspect,
        seed=seed
    )


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate artist photos")
    parser.add_argument("artist", help="Artist name (nova, blade, velvet, rust, phoenix, ghost, zephyr)")
    parser.add_argument("--framing", default="headshot", choices=["profile", "headshot", "shoulders", "torso", "full_body"])
    parser.add_argument("--quality", default="high", choices=["draft", "normal", "high", "ultra"])
    parser.add_argument("--seed", type=int)
    
    args = parser.parse_args()
    
    path = generate_artist_photo(
        artist=args.artist,
        framing=args.framing,
        quality=args.quality,
        seed=args.seed
    )
    print(f"✨ Photo saved: {path}")


if __name__ == "__main__":
    main()
