"""
Scrapers package for MTG price scraping

Import all scrapers here to make them easily accessible
"""

from .cryptmtg_scraper import CryptMTGScraper
from .magicarte_scraper import MagiCarteScraper
from .facetofacegames_scraper import FaceToFaceGamesScraper

__all__ = [
    "CryptMTGScraper",
    "MagiCarteScraper",
    "FaceToFaceGamesScraper",
]
