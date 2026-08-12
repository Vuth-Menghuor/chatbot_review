from typing import Any

from app.schemas.normalized_chat import KeyValueBlock
from app.services.normalizers.calculator.formatting import (
    key_value_items_from_bullets,
    key_value_items_from_mapping,
)


def product_key_value_block(result: dict[str, Any]) -> KeyValueBlock | None:
    product = result.get("product") if isinstance(result.get("product"), dict) else {}
    if not product:
        return None
    return KeyValueBlock(title="Product Information", items=key_value_items_from_mapping(product))


def input_key_value_block(result: dict[str, Any]) -> KeyValueBlock | None:
    inputs = result.get("inputs") if isinstance(result.get("inputs"), dict) else {}
    if not inputs:
        return None
    return KeyValueBlock(title="Input Parameters", items=key_value_items_from_mapping(inputs))


def product_key_value_block_from_legacy_sections(sections: dict[str, list[str]]) -> KeyValueBlock | None:
    items = key_value_items_from_bullets(sections.get("PRODUCT INFORMATION", []))
    return KeyValueBlock(title="Product Information", items=items) if items else None


def input_key_value_block_from_legacy_sections(sections: dict[str, list[str]]) -> KeyValueBlock | None:
    items = key_value_items_from_bullets(sections.get("INPUT PARAMETERS", []))
    return KeyValueBlock(title="Input Parameters", items=items) if items else None
