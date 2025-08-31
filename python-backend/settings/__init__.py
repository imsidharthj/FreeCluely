"""
Settings Management module for Horizon Overlay.
Handles configuration persistence, user preferences, and validation.
GUI/THEME REMOVED: Theme management moved to frontend for UI-specific handling.
"""

from .settings_manager import SettingsManager
from .user_preferences import UserPreferences
from .config_validator import ConfigValidator
# REMOVED: from .theme_manager import ThemeManager - Theme logic moved to frontend

__all__ = [
    "SettingsManager",
    "UserPreferences",
    "ConfigValidator"
    # REMOVED: "ThemeManager" - Theme logic moved to frontend
]