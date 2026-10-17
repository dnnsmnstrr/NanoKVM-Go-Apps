"""Bad Apple!! shadow-art video, 1-bit at 30 FPS (packed with tools/pack_frames.py)."""

from pathlib import Path

from engine import VideoClip

CLIP = VideoClip("bad-apple", "Bad Apple", Path(__file__).resolve().parent.parent / "assets" / "bad-apple.bin",
                 order=10)
