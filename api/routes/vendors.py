from fastapi import APIRouter

from api.models import VendorMeta
from cart.cart_handler import CartHandler

router = APIRouter()


@router.get("/vendors", response_model=list[VendorMeta])
def list_vendors() -> list[VendorMeta]:
    return [
        VendorMeta(
            name=v.name,
            shipping_cost=v.shipping_cost,
            fulfillment_label=v.fulfillment_label,
            supports_bulk_add=v.supports_bulk_add,
            deck_builder_url=v.deck_builder_url,
        )
        for v in CartHandler.VENDORS.values()
    ]
