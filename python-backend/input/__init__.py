"""
Input Event Management module for Horizon Overlay.
VOICE REMOVED: Voice input capture moved to frontend, transcription handled by backend API.
HOTKEYS REMOVED: Hotkey management moved to frontend for platform-specific handling.
"""

from .shortcut_config import ShortcutConfig

__all__ = [
    "ShortcutConfig"
    # REMOVED: "VoiceInputManager" - Voice capture now frontend-only, transcription via API
]