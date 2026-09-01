import re
from typing import Optional, Dict

# Shared lists of countries and prefix families to filter out non-product descriptions
_TRADE_COUNTRIES = frozenset([
    "cambodia", "vietnam", "thailand", "china", "laos", "myanmar", "malaysia", "singapore", 
    "indonesia", "philippines", "brunei", "japan", "korea", "usa", "america", "europe", 
    "india", "germany", "france", "uk", "united kingdom", "australia", "canada"
])

_TYPO_GAZETTEER_COUNTRIES = frozenset(_TRADE_COUNTRIES)
_TYPO_GAZETTEER_DOMAIN = frozenset([
    "hs", "hscode", "hs-code", "code", "codes", "customs",
    "duty", "duties", "tax", "taxes", "tariff", "tariffs",
    "trade", "import", "export", "calculate", "calculation",
    "classification", "procedure", "policy", "regulation",
    "rice", "vehicle", "product", "laptop", "phone",
    "computer", "electronics", "gdce", "gdce-intern",
])
_TYPO_GAZETTEER_BRANDS = frozenset([
    "bmw", "toyota", "honda", "mazda", "nissan", "hyundai",
    "kia", "mitsubishi", "suzuki", "isuzu", "mercedes",
    "volkswagen", "audi", "ford", "chevrolet", "peugeot",
    "volvo", "renault", "subaru", "lexus", "infiniti",
    "jaguar", "landrover",
])

_TYPO_PROTECTED_TERMS = frozenset().union(
    _TYPO_GAZETTEER_COUNTRIES,
    _TYPO_GAZETTEER_DOMAIN,
    _TYPO_GAZETTEER_BRANDS,
)

_TYPO_CORRECTION_TERMS = frozenset([
    "bmw", "toyota", "honda", "mazda", "nissan", "hyundai",
    "kia", "mitsubishi", "suzuki", "isuzu", "mercedes",
    "volkswagen", "audi", "ford", "chevrolet", "peugeot",
    "volvo", "renault", "subaru", "lexus", "infiniti",
    "jaguar", "landrover", "trade", "data", "import", "export",
    "customs", "duty", "tax", "tariff", "calculate", "calculation",
    "classification", "procedure", "policy", "regulation", "lookup",
    "search", "find", "product", "vehicle", "rice", "laptop",
    "phone", "computer", "electronics", "gdce", "gdce-intern",
])

_TYPO_CORRECTION_GREETINGS = frozenset([
    "hello", "hi", "hey", "hiya", "howdy"
])

_TYPO_CORRECTION_TERMS = frozenset().union(
    _TYPO_CORRECTION_TERMS,
    _TYPO_CORRECTION_GREETINGS,
)

_NON_PRODUCT_PREFIXES = (
    "regulat",   # regulate, regulation, regulatory, regulator
    "procedur",  # procedure, procedures, procedural
    "document",  # document, documents, documentation, documented
    "certif",    # certificate, certification, certified
    "declar",    # declare, declaration, declarant
    "clearanc",  # clearance, clearances
)

# Escape hatch constants for turn-2 clarification responses
ENGLISH_ESCAPE_HATCH_SET = frozenset([
    "whatever", "idk", "don't know", "dont know", "anything", "any", 
    "latest", "default", "overall", "total", "no specific", "skip", "idk man"
])

KHMER_ESCAPE_HATCH_SET = frozenset([
    "មិនដឹង", "អត់ដឹង", "ណាមួយក៏បាន", "អីក៏បាន", "ធម្មតា", "មិនដឹងទេ",
    "min deng", "ot deng", "ey kor ban", "namaoy kor ban"
])

ALL_ESCAPE_HATCH_TERMS = ENGLISH_ESCAPE_HATCH_SET | KHMER_ESCAPE_HATCH_SET
MAX_PRODUCT_ASK_BACK_RETRIES = 2

# Stop words stripped when extracting expected terms from clarifying questions.
_CLARIFY_STOP_WORDS = frozenset([
    "is", "the", "a", "an", "or", "as", "and", "of", "for", "are", "does",
    "do", "was", "with", "its", "this", "that", "your", "it", "in", "to",
    "has", "have", "can", "will", "be", "if", "not", "from", "you", "how",
    "what", "which", "who", "where", "when", "why", "whose", "whom",
])

# Generic nouns that survive stop-word stripping but are too broad to be
# useful as merge-eligibility signals
_CLARIFY_GENERIC_NOUNS = frozenset([
    "vehicle", "product", "item", "type", "unit", "specify", "details",
    "model", "specific", "question", "questions", "classification",
    "code", "codes", "tariff", "tariffs", "goods", "import", "export",
    "imported", "exported", "use", "used",
    "wheel", "wheels", "drive", "built", "kits", "kit", "four", "two", "three", "one", "first", "second", "third",
    "number", "numbers", "option", "options", "select", "choice", "choices", "equipped",
    "completely", "knocked", "down", "fully",
])

# Category-specific technical discriminators
_SPEC_DISCRIMINATORS: Dict[str, frozenset] = {
    "vehicle": frozenset([
        "petrol", "diesel", "electric", "hybrid", "ev", "battery",
        "engine", "cc", "kw", "hp", "4wd", "cbu", "ckd",
    ]),
    "food": frozenset([
        "fresh", "frozen", "airtight", "salted", "dried", "smoked",
        "prepared", "preserved",
    ]),
    "textile": frozenset([
        "knitted", "woven", "crocheted", "wool", "synthetic",
        "cotton", "artificial",
    ]),
}

# Words that indicate the user already wrote a full question/statement
_QUESTION_SIGNALS = frozenset([
    "what", "which", "where", "when", "who", "how", "why",
    "is", "are", "can", "does", "do", "tell", "find",
    "hs", "code", "tariff", "import", "export", "classify",
    "calculate", "duty", "rate", "definition",
    "hello", "hi", "hey", "hiya", "howdy",
    "bye", "goodbye", "farewell", "ciao",
    "good", "morning", "afternoon", "evening", "night",
    "thanks", "thank", "please", "sorry", "excuse",
    "yes", "no", "ok", "okay", "sure", "noted", "nope", "yep"
])


class Heuristics:
    @staticmethod
    def normalize_turn2_input(text: str) -> str:
        if not text:
            return ""
        return text.lower().strip()

    @staticmethod
    def is_turn2_escape_hatch(text: str) -> bool:
        if not text:
            return False
        cleaned = text.strip().lower().replace("?", "")
        return cleaned in ALL_ESCAPE_HATCH_TERMS

    @staticmethod
    def is_vague_trade_query(query: str) -> bool:
        """Determines if query is too vague to perform RAG or query calculation without clarification."""
        q_lower = (query or "").lower().strip()
        # Remove common conversational fillers
        fillers = {"can", "you", "help", "me", "with", "tell", "about", "assist", "please", "get", "show", "to", "for", "with"}
        clean_tokens = [t for t in re.findall(r"[a-z\u1780-\u17FF]+", q_lower) if t not in fillers]
        clean_query = " ".join(clean_tokens)
        
        vague_queries = {
            "trade", "trade data", "trade volume", "statistics", "trade statistics",
            "import export", "import", "export", "ទិន្នន័យពាណិជ្ជកម្ម", "poanichakam"
        }
        if clean_query in vague_queries or q_lower in vague_queries:
            return True
            
        tokens = set(re.findall(r"[a-z]+", q_lower))
        if len(tokens) == 2 and "data" in tokens and ("trade" in tokens or "import" in tokens or "export" in tokens):
            return True
        if len(tokens) == 1 and q_lower in _TRADE_COUNTRIES:
            return True
        return False

    @staticmethod
    def looks_like_commercial_description(text: str) -> bool:
        """
        Structural heuristic to detect if text appears to be copied from a logistics sheet,
        shipping manifest, or commercial product listing.
        """
        if not text: 
            return False
        
        low = text.lower()
        spec_unit_pattern = re.compile(
            r"\b(?:\d+[\.\d]*\s*cc|cc\b|\d+[\.\d]*\s*(?:wh|kwh|v|ah)\b|\d+\s*seats?\b|\d+\s*wheels?\b|(?:19|20)\d{2}\b|\d+\s*(?:g|kg|ml|l|pcs|bags|ctn)\s*x\s*\d+)\b", 
            re.IGNORECASE
        )
        model_code_pattern_case_sensitive = re.compile(r"\b[A-Z]{4,}\b|\(\d+\)")
        model_code_pattern_case_insensitive = re.compile(
            r"\b[a-z0-9]{2,}[0-9][a-z0-9]*\b|\b[a-z][0-9]\b|\b[0-9][a-z]\b",
            re.IGNORECASE
        )
        commercial_words = {
            "new", "used", "moto", "auto", "electric", "hybrid", "plug", "diesel", "petrol", "lpg", "cng", 
            "hev", "bev", "phev", "ckd", "ikd", "cbp",  
            "sedan", "suv", "van", "truck", "bus", "wheel", "seat", "door", "battery",  
            "tea", "bag", "bags", "powder", "powdered", "whole", "rice", "food", "pack", "packs", "box",  
            "frozen", "fresh", "organic", "grade",
            "car", "sports", "competition", "salmon", "fillet", "fish", "meat", "seafood",
            "textile", "garment", "apparel", "clothing", "cotton", "wool", "polyester",
            "laptop", "phone", "tablet", "computer", "electronics"
        }
        
        has_spec = bool(spec_unit_pattern.search(low))
        has_model = bool(
            model_code_pattern_case_sensitive.search(text)
            or model_code_pattern_case_insensitive.search(text)
        )
        words_set = set(re.findall(r"[a-z]+", low))
        descriptor_hits = len(words_set & commercial_words)
        
        return sum([has_spec, has_model, descriptor_hits >= 1]) >= 2 or descriptor_hits >= 2

    @staticmethod
    def looks_like_trade_data_query(query: str) -> bool:
        q_lower = (query or "").lower()
        disqualifiers = ["hs code", "tariff code", "classify", "classification", 
                        "calculate", "duty", "tax", "vat", "fee", "regulation", "procedure"]
        if any(token in q_lower for token in disqualifiers): 
            return False
        has_year = re.search(r"\b20\d{2}\b", q_lower) is not None
        has_trade_flow = re.search(r"\b(import|imports|imported|im|export|exports|exported|ex)\b", q_lower) is not None
        has_relation = re.search(r"\b(from|to|between|with|vs|versus)\b", q_lower) is not None
        has_trade_term = re.search(r"\b(trade|volume|flow|shipment|shipping|cargo|freight|data)\b", q_lower) is not None
        
        return bool(has_year and ((has_trade_flow and has_relation) or has_trade_term))

    @staticmethod
    def looks_like_short_product_lookup(query: str) -> bool:
        normalized = (query or "").strip().lower()
        if not normalized: 
            return False
        disqualifiers = ["hs", "code", "classify", "classification", "calculate", "duty", "tax", "import", "export", "importing", "exporting", "trade", "regulation", "policy", "procedure", "what is", "define", "explain", "how much", "between", "from", "to", "cost", "costly", "cheaper", "expensive", "better", "worse", "which", "recommend", "recommendation", "one"]
        if any(re.search(rf"\b{re.escape(tok)}\b", normalized) for tok in disqualifiers):
            return False
        if re.match(r"^(but|and|so|then)?\s*(what|how|which|where|when|why|can|could|is|are|do|does)\b", normalized): 
            return False
        tokens = re.findall(r"[a-z0-9]+", normalized)
        if not tokens or len(tokens) > 6: 
            return False
        _BUILD_FORMAT_ABBREVS = {"cbu", "ckd", "skd"}
        if len(tokens) == 1 and tokens[0] in _BUILD_FORMAT_ABBREVS:
            return False
        blocked_tokens = {"hello", "hi", "hey", "thanks", "please", "weather", "time", "date", "football", "soccer", "movie", "music", "recipe", "cook", "joke", "politics", "war", "crime", "hack", "hacking", "investment", "stock"}
        if any(token in blocked_tokens for token in tokens):
            return False
        if re.match(r"^(h[aeiou]{2,}|hey+|hell[o]+|hi+)$", normalized):
            return False
        if any(token in _TRADE_COUNTRIES for token in tokens):
            return False
        if any(token.startswith(_NON_PRODUCT_PREFIXES) for token in tokens):
            return False
        if all(token.isdigit() for token in tokens):
            return False
        return True

    @staticmethod
    def is_slot_fragment_reply(user_text: str, clarification_intents: list) -> bool:
        """
        Structural heuristic: returns True if user response matches the expected technical
        format/vocabulary of a slot-filling or specification-fragment response.
        """
        low = user_text.lower().strip()
        if not low:
            return False
        
        # 1. Parameter patterns: match numeric specifications with units (e.g. "cif=$1000", "2000cc", "19 seats")
        params_pattern = re.compile(
            r"^(?:cif|fob|value|price|cost|tax|duty|tariff|vat|fee|engine|size)?\s*(?:is|are)?\s*[:=\s]*\$?\d+[\d,.]*\s*(?:usd|khr|dollars|cc|wh|seats?|wheels?|ctn|pcs|bags)?$", 
            re.IGNORECASE
        )
        if params_pattern.match(low):
            return True
            
        # 2. Match a bare numeric value (e.g. "2000", "15000", "12")
        numeric_clean = low.replace(",", "").replace("$", "").strip()
        if numeric_clean.isdigit():
            return True

        # 2.5. Match a dotted or numeric HS code pattern (e.g. "6109.10.10", "61091010", "hs 6109.10.10")
        # Ensure it is a valid HS code pattern (4, 6, or 8 digits with dots) and NOT a simple decimal price.
        if re.search(r"\b(?:hs\s*code|hs)?\s*(?:\d{4}\.\d{2}\.\d{2}|\d{8})\b", low):
            return True
        if re.search(r"\b(?:hs\s*code|hs)\s*\d{4}\.\d{2}\b", low):
            return True
        if re.search(r"\b\d{4}\.\d{2}\b", low) and not re.search(r"[\$\u17db€£\d\.]+\s*(?:usd|khr|eur|gbp|cif|fob)|\b(?:cif|fob|usd|khr)\b", low):
            if not low.endswith(".00"):
                return True

        # 3. Match single-word country names or country list matches
        if low in _TRADE_COUNTRIES:
            return True

        # 4. Filter out prefix families of general non-product queries
        if any(low.startswith(p) for p in _NON_PRODUCT_PREFIXES):
            return False

        # 5. Build-format abbreviation matches
        if low in {"cbu", "ckd", "skd", "fbu"}:
            return True

        # 5.5. Match ordinal selection patterns (e.g. "use the first one", "first option")
        selection_patterns = [
            r"^(?:use\s+)?(?:the\s+)?(?:first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|one|two|three|four|five|1|2|3|4|5)(?:\s+one|\s+option|\s+candidate)?$",
            r"^option\s+\d+$",
            r"^number\s+\d+$"
        ]
        if any(re.match(pat, low) for pat in selection_patterns):
            return True

        # 6. Check if it is a general question starter
        if any(re.search(rf"\b{re.escape(sig)}\b", low) for sig in _QUESTION_SIGNALS):
            return False

        # 7. Check if user is trying to look up a generic product lookup (e.g. "import sedan car")
        if Heuristics.looks_like_short_product_lookup(user_text):
            return True

        # 8. Check if user responds with a known specification discriminator (e.g. "petrol", "diesel", "frozen")
        words = set(re.findall(r"[a-z]+", low))
        for category, spec_words in _SPEC_DISCRIMINATORS.items():
            if words & spec_words:
                return True

        return False

    @staticmethod
    def is_genuine_conversational_small_talk(query: str) -> bool:
        low = (query or "").strip().lower()
        if not low:
            return False

        GREETING_PATTERNS = [
            r"\bhi+\b", r"\bhey+\b", r"\bhello+\b", r"\byo+\b",
            r"\bgreetings\b", r"\bhowdy\b", r"\bbello+\b", r"\bhelo+\b",
            r"\bgood\s+morning\b", r"\bgood\s+afternoon\b", r"\bgood\s+evening\b",
        ]
        FAREWELL_PATTERNS = [
            r"\bbye\b", r"\bgoodbye\b", r"\bfarewell\b", r"\bsee\s+you\b",
            r"\btake\s+care\b",
        ]
        GRATITUDE_PATTERNS = [
            r"\bthanks\b", r"\bthank\s+you\b", r"\bthx\b", r"\bty\b",
            r"\bappreciate\b", r"\bthank\s+u\b",
        ]
        CASUAL_PATTERNS = [
            r"\bhow\s+are\s+(?:you|u)\b", r"\bwhats\s+up\b", r"\bhow\s+is\s+your\s+day\b",
            r"\bhows\s+it\s+going\b", r"\bnice\s+to\s+meet\s+(?:you|u)\b",
            r"\bpleasure\s+to\s+meet\s+(?:you|u)\b", r"\btell\s+me\s+a\s+joke\b",
            r"\bjoke\b", r"\broast\s+me\b",
        ]
        IDENTITY_PATTERNS = [
            r"\b(what|who)\s+are\s+(?:you|u)\b",
            r"\bwhat\s+is\s+your\s+(name|purpose)\b",
            r"\bwhat\s+(can|do)\s+(?:you|u)\s+do\b",
            r"\bare\s+(?:you|u)\s+(a\s+)?(bot|ai|robot|chatbot|assistant|human|real)\b",
            r"\btell\s+me\s+about\s+yourself\b",
            r"\b(what\s+are\s+)?your\s+capabilities\b",
            r"\b(how|what)\s+can\s+(?:you|u)\s+help\b",
        ]
        CONFIRMATION_PATTERNS = [
            r"^(ok|okay|got\s+it|sure|alright|noted|sounds\s+good|perfect|great)\s*\.?$",
        ]
        all_en_patterns = (
            GREETING_PATTERNS + FAREWELL_PATTERNS + GRATITUDE_PATTERNS
            + CASUAL_PATTERNS + IDENTITY_PATTERNS + CONFIRMATION_PATTERNS
        )
        if any(re.search(pat, low) for pat in all_en_patterns):
            return True

        KHMER_CONVERSATIONAL_TOKENS = [
            "សួស្តី", "ជំរាបសួរ", "អរគុណ", "សូមអរគុណ", "លាហើយ",
            "ជំរាបលា", "ល្អ", "យល់ព្រម", "បាទ", "ចាស",
        ]
        original = (query or "").strip()
        if any(token in original for token in KHMER_CONVERSATIONAL_TOKENS):
            return True

        return False
