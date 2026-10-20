"""分层世界里的采办：宏观变得慢，微观变得快。这里只有世界和玩法；几种采办和跑分在 stratabench。"""

from .config import load
from .game import play
from .view import View
from .world import World

__all__ = ["View", "World", "load", "play"]
