"""Map marker pictures and icons for tracked vessels."""
from __future__ import annotations

from urllib.parse import quote

from .const import SHIP_CATEGORIES, STATIONARY_SOG_KNOTS, ship_category
from .coordinator import ShipData

# Navigational status codes for "at anchor" and "moored".
_BERTHED_STATUSES = (1, 5)

_ARROW = (
    '<path d="M16 3 L25 28 L16 22 L7 28 Z" fill="{color}" stroke="#fff"'
    ' stroke-width="2" stroke-linejoin="round" transform="rotate({angle} 16 16)"/>'
)
_DOT = '<circle cx="16" cy="16" r="8" fill="{color}" stroke="#fff" stroke-width="2"/>'


def ship_icon(ship: ShipData) -> str:
    """Return an mdi icon matching the vessel's category and status."""
    if ship.navigational_status in _BERTHED_STATUSES:
        return "mdi:anchor"
    return SHIP_CATEGORIES[ship_category(ship.ship_type)][1]


def ship_picture(ship: ShipData) -> str:
    """Return an SVG data URI: an arrow pointing where the vessel is heading,
    or a dot when it is not moving, coloured by vessel category."""
    color = SHIP_CATEGORIES[ship_category(ship.ship_type)][0]
    angle = ship.true_heading if ship.true_heading is not None else ship.cog
    moving = (
        angle is not None
        and (ship.sog or 0) >= STATIONARY_SOG_KNOTS
        and ship.navigational_status not in _BERTHED_STATUSES
    )
    shape = (
        _ARROW.format(color=color, angle=round(angle))
        if moving
        else _DOT.format(color=color)
    )
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">{shape}</svg>'
    return "data:image/svg+xml," + quote(svg)
