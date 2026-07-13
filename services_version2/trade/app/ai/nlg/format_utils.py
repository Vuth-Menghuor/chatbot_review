"""Shared text formatting and phrase generation utilities for NLG."""

from typing import Any, Dict, List


def format_usd(val: float) -> str:
    """Format USD value to a human readable abbreviation."""
    if val >= 1e9:
        return f"${val / 1e9:.2f} billion"
    elif val >= 1e6:
        return f"${val / 1e6:.2f} million"
    elif val > 0:
        return f"${val:,.2f}"
    return "$0.00"


def format_weight(val: float) -> str:
    """Format kg value to a human readable abbreviation."""
    if val >= 1e6:
        return f"{val / 1e6:,.2f} million kg"
    elif val > 0:
        return f"{val:,.2f} kg"
    return "0 kg"


def format_metric(value: float, metrics: List[str], value_col: str = "") -> str:
    """Format value based on requested metrics (weight vs value)."""
    if value_col and "weight" in value_col.lower():
        return format_weight(value)
    if any("weight" in str(m).lower() for m in metrics):
        return format_weight(value)
    return format_usd(value)


def generate_capped_list_message(records: List[Dict[str, Any]], label_col: str = "label", value_col: str = "trade_value_usd", top_n_to_name: int = 5, metrics: List[str] = None) -> str:
    """Generate summary phrase for a list of items, capping at N names."""
    total_count = len(records)
    if total_count == 0:
        return ""
    named_items = records[:top_n_to_name]

    def get_label(r):
        lbl = r.get(label_col) or "Unknown"
        if isinstance(lbl, str):
            lbl = lbl.strip().replace('\r', '').replace('\n', '').strip()
        return lbl

    if len(named_items) == 1:
        lbl = get_label(named_items[0])
        val = named_items[0].get(value_col) or 0.0
        val_str = format_metric(val, metrics or ["VALUE_USD"], value_col=value_col)
        return f"led by {lbl} at {val_str}"

    item_phrases = []
    for r in named_items:
        lbl = get_label(r)
        val = r.get(value_col) or 0.0
        val_str = format_metric(val, metrics or ["VALUE_USD"], value_col=value_col)
        item_phrases.append(f"{lbl} at {val_str}")

    summary_phrase = ", ".join(item_phrases[:-1]) + f", and {item_phrases[-1]}"
    if total_count > top_n_to_name:
        return f"led by {summary_phrase}, among the top {total_count} shown below"
    return f"led by {summary_phrase}"


def generate_ranking_message(records: List[Dict[str, Any]], label_col: str = "label", value_col: str = "trade_value_usd", top_n_to_name: int = 5, metrics: List[str] = None) -> str:
    """Wrapper around generate_capped_list_message for rankings."""
    return generate_capped_list_message(records, label_col, value_col, top_n_to_name, metrics)


def get_direction_phrase(flow: str, partner: Any) -> str:
    """Get dynamic phrase for flow direction and partner country."""
    if flow == "export":
        flow_phrase = "Exports"
        prep = "to"
    elif flow == "import":
        flow_phrase = "Imports"
        prep = "from"
    else:
        flow_phrase = "Total trade"
        prep = "with"

    if not partner:
        return flow_phrase

    if isinstance(partner, list):
        partner_str = ", ".join(partner)
    else:
        partner_str = str(partner)

    return f"{flow_phrase} {prep} {partner_str}"


def get_product_phrase(facts: Dict[str, Any]) -> str:
    """Format product label dynamically."""
    prod = facts.get("sitc_division") or facts.get("sitc_section") or facts.get("hs_code") or facts.get("hs_chapter")
    if prod:
        from app.registry.product_resolver import resolve_hs_to_name
        friendly = resolve_hs_to_name(str(prod))
        if friendly:
            return f" of {friendly}"

        if facts.get("sitc_division"):
            return f" of SITC Division {prod}"
        if facts.get("sitc_section"):
            return f" of SITC Section {prod}"
        if facts.get("hs_code"):
            return f" of HS Code {prod}"
        return f" of HS Chapter {prod}"
    return ""


def get_transport_phrase(transport: Any) -> str:
    """Get transport phrase if present."""
    if transport:
        return f" via {transport}"
    return ""
