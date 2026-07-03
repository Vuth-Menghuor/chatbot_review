TRANSPORT_MODE_LABELS: dict[str, str] = {
    "1": "sea",
    "2": "rail",
    "3": "road",
    "4": "air",
    "5": "postal",
    "6": "multimodal",
    "7": "fixed",
    "8": "inland waterway",
    "9": "other transport",
    "0": "unknown",
}

TRANSPORT_MODE_DISPLAY_NAMES: dict[str, str] = {
    "1": "Sea transport",
    "2": "Rail transport",
    "3": "Road transport",
    "4": "Air transport",
    "5": "Postal",
    "6": "Multimodal",
    "7": "Fixed",
    "8": "Inland waterway",
    "9": "Other transport",
    "0": "Unknown",
}

TRANSPORT_MODE_SYNONYMS: dict[str, list[str]] = {
    "1": ["sea", "ocean", "ship", "vessel", "maritime"],
    "2": ["rail", "train"],
    "3": ["road", "land", "truck"],
    "4": ["air", "plane", "flight"],
    "5": ["postal", "post", "mail"],
    "6": ["multimodal", "multi-modal"],
    "7": ["fixed", "pipeline"],
    "8": ["inland", "river", "canal"],
    "9": ["other transport", "not elsewhere specified", "nes", "unclassified transport"],
    "0": ["unknown", "unspecified"],
}