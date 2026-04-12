from fastapi import APIRouter

from api.models import CardModel, ParseRequest
from scraper_config import create_custom_config
from scraper_manager import ScraperManager

router = APIRouter()


@router.post("/parse", response_model=list[CardModel])
def parse_cards(req: ParseRequest) -> list[CardModel]:
    config = create_custom_config(scrapers=[], headless=True)
    manager = ScraperManager(config)
    cards = manager.parse_moxfield_format(req.card_list)
    return [
        CardModel(
            quantity=c.quantity,
            name=c.name,
            set_code=c.set_code,
            collector_number=c.collector_number,
        )
        for c in cards
    ]
