"""Visual search endpoint.

``POST /search/visual`` — upload a garment photo and get the nearest in-catalog,
in-stock products ("shop the look from an image"). Optional form fields apply the
same constraints as text recommendations (category, colour, size, gender,
budget). Returns JSON (the Phase-6 widget renders it; streaming isn't needed for
a search result).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from app.api.ratelimit import enforce_rate_limit
from app.api.widget import enforce_widget_token
from app.observability.logging import get_logger
from app.recommendations.constraints import Constraints
from app.services.container import Container

router = APIRouter(tags=["visual"])
_log = get_logger("visual_api")

_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB upload cap


def _container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


@router.post(
    "/search/visual",
    summary="Find products similar to an uploaded image",
    dependencies=[Depends(enforce_rate_limit), Depends(enforce_widget_token)],
)
async def visual_search(
    request: Request,
    image: Annotated[UploadFile, File(description="Garment photo to match")],
    category: Annotated[str | None, Form()] = None,
    color: Annotated[str | None, Form()] = None,
    size: Annotated[str | None, Form()] = None,
    gender: Annotated[str | None, Form()] = None,
    budget_max: Annotated[float | None, Form()] = None,
) -> dict[str, Any]:
    """Return visually similar, in-stock products for the uploaded image."""
    container = _container(request)
    if container.visual_search is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Visual search is not enabled.",
        )

    data = await image.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty image upload.")
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image too large.")

    constraints = Constraints(
        category=category,
        color=color,
        size=size,
        gender=gender,
        budget_max=budget_max,
    )
    results = await container.visual_search.search(data, constraints)
    return {
        "count": len(results),
        "results": [
            {
                "product_id": r.product_id,
                "title": r.title,
                "price": r.price,
                "url": r.url,
                "reason": r.reason,
            }
            for r in results
        ],
    }
