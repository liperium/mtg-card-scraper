from fastapi import APIRouter, HTTPException

from api.models import CartFormatRequest, CartFormatResponse
from base_vendor import CartItem
from cart.cart_handler import CartHandler

router = APIRouter()


@router.post("/cart/format", response_model=CartFormatResponse)
def format_cart(req: CartFormatRequest) -> CartFormatResponse:
    vendor = CartHandler.VENDORS.get(req.store_name)
    if not vendor:
        raise HTTPException(status_code=404, detail=f"Unknown store: {req.store_name}")

    items = [
        CartItem(
            card_name=item.card,
            quantity=item.quantity,
            price_per_unit=item.price_per_unit,
            total_price=item.total_price,
        )
        for item in req.buy_list
    ]

    return CartFormatResponse(
        url=vendor.deck_builder_url,
        card_list=vendor.format_card_list(items),
        supports_bulk_add=vendor.supports_bulk_add,
    )
