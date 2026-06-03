"""Map human-friendly extracted params to DAL-ready params.

No database or HTTP dependencies.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

TRANSPORT_CODE_MAP = {
    "air": "4",
    "sea": "1",
    "land": "3",
    "road": "3",
    "rail": "2",
    "inland": "8",
    "postal": "5",
    "multimodal": "6",
    "fixed": "7",
}

DIRECTION_CODE_MAP = {
    "export": "EX",
    "exports": "EX",
    "import": "IM",
    "imports": "IM",
}

GROUP_DIMENSION_MAP = {
    "origin_country": "PARTNER_COUNTRY",
    "destination_country": "PARTNER_COUNTRY",
    "mode_of_transport": "MODE_OF_TRANSPORT",
    "hs_code": "HS_CHAPTER",
    "hs_chapter": "HS_CHAPTER",
    "hs_heading": "HS_HEADING",
    "trade_direction": "FLOW",
    "partner_country": "PARTNER_COUNTRY",
    "flow": "FLOW",
}


def transform_params_for_dal(raw_params: dict[str, Any]) -> dict[str, Any]:
    """Convert extracted NL params into DAL-compatible keys and codes."""
    params = dict(raw_params)
    intent = params.get("intent", "summary")

    # Transport mode: 'air' → '4'
    mot = params.get("mode_of_transport")
    if mot:
        params["mode_of_transport"] = TRANSPORT_CODE_MAP.get(mot.lower().strip(), mot)

    # Trade direction: 'export' → 'EX'
    direction = params.get("trade_direction")
    if direction:
        params["trade_direction"] = DIRECTION_CODE_MAP.get(direction.lower().strip(), direction.upper())

    # Normalize base country when it's the only country mentioned
    origin = params.get("origin_country")
    dest = params.get("destination_country")
    direction = params.get("trade_direction")
    if direction:
        if direction == "IM" and origin == "KH" and not dest:
            params["origin_country"] = None
            params["destination_country"] = "KH"
        elif direction == "EX" and dest == "KH" and not origin:
            params["destination_country"] = None
            params["origin_country"] = "KH"

    # Country perspective correction (Cambodia-centric)
    # Skip for comparison intent — both countries are partner countries
    origin = params.get("origin_country")
    dest = params.get("destination_country")
    direction = params.get("trade_direction")
    if direction and intent != "comparison":
        should_flip = False
        if direction == "EX":
            if (origin and origin.upper() != "KH") or (dest and dest.upper() == "KH"):
                should_flip = True
        elif direction == "IM":
            if (dest and dest.upper() != "KH") or (origin and origin.upper() == "KH"):
                should_flip = True
        if should_flip:
            params["trade_direction"] = "IM" if direction == "EX" else "EX"

    # Now, fill in Cambodia ("KH") as the implicit base for the finalized direction
    direction = params.get("trade_direction")
    if direction and intent != "comparison" and intent != "trade_balance":
        if direction == "EX":
            if not params.get("origin_country"):
                params["origin_country"] = "KH"
            if not params.get("destination_country") and params.get("origin_country") != "KH":
                params["destination_country"] = params["origin_country"]
                params["origin_country"] = "KH"
        elif direction == "IM":
            if not params.get("destination_country"):
                params["destination_country"] = "KH"
            if not params.get("origin_country") and params.get("destination_country") != "KH":
                params["origin_country"] = params["destination_country"]
                params["destination_country"] = "KH"

    # For comparison intent: both countries become partner_countries list
    if intent == "comparison" and (origin or dest):
        countries = []
        if origin:
            countries.append(origin)
        if dest and dest not in countries:
            countries.append(dest)
        if countries:
            params["partner_countries"] = countries

        # Align origin_country and destination_country to reflect the Cambodia-centric flow
        if direction == "EX":
            params["origin_country"] = "KH"
            params["destination_country"] = None
        elif direction == "IM":
            params["origin_country"] = None
            params["destination_country"] = "KH"
        else:
            params["origin_country"] = None
            params["destination_country"] = None

    # Map group_by / dimensions if provided as friendly names
    group_by = params.get("group_by")
    if isinstance(group_by, list):
        params["group_by"] = [GROUP_DIMENSION_MAP.get(g, g) for g in group_by]

    dimensions = params.get("dimensions")
    if isinstance(dimensions, list):
        params["dimensions"] = [GROUP_DIMENSION_MAP.get(d, d) for d in dimensions]

    return params
