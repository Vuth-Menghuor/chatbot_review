"""Generate 150+ comprehensive test cases for accuracy testing of GDCE Trade ChatBot."""

import json
from pathlib import Path

def generate_all_cases():
    cases = []
    case_id = 1

    # 1. SUMMARY INTENT (23 cases)
    summary_questions = [
        # Simple and Standard
        ("What was Cambodia's total export value in 2025?", {"intent": "summary", "origin_country": "KH", "trade_direction": "EX", "year": 2025}, {"dimensions": "FLOW", "period": "2025", "filter": ["FLOW:eq:EX"]}),
        ("What was Cambodia's total import value in 2024?", {"intent": "summary", "origin_country": "KH", "trade_direction": "IM", "year": 2024}, {"dimensions": "FLOW", "period": "2024", "filter": ["FLOW:eq:IM"]}),
        ("Show total imports in 2023", {"intent": "summary", "trade_direction": "IM", "year": 2023}, {"dimensions": "FLOW", "period": "2023", "filter": ["FLOW:eq:IM"]}),
        ("Show total exports for Cambodia in 2025", {"intent": "summary", "trade_direction": "EX", "year": 2025}, {"dimensions": "FLOW", "period": "2025", "filter": ["FLOW:eq:EX"]}),
        
        # Product & Country Aliases
        ("What was the total export value of Cambodian rice in 2025?", {"intent": "summary", "trade_direction": "EX", "hs_code": "1006", "year": 2025}, {"dimensions": "FLOW", "period": "2025", "filter": ["FLOW:eq:EX", "HS_HEADING:eq:1006"]}),
        ("How much milled rice did Cambodia import in 2024?", {"intent": "summary", "trade_direction": "IM", "hs_code": "1006", "year": 2024}, {"dimensions": "FLOW", "period": "2024", "filter": ["FLOW:eq:IM", "HS_HEADING:eq:1006"]}),
        ("What was the value of electronics imports from China in 2025?", {"intent": "summary", "trade_direction": "IM", "origin_country": "CN", "hs_code": "8517", "year": 2025}, {"dimensions": "FLOW", "period": "2025", "filter": ["PARTNER_COUNTRY:eq:CN", "FLOW:eq:IM", "HS_HEADING:eq:8517"]}),
        ("Show total export of garments (HS 61) to the United States in 2024", {"intent": "summary", "trade_direction": "EX", "destination_country": "US", "hs_chapter": "61", "year": 2024}, {"dimensions": "FLOW", "period": "2024", "filter": ["PARTNER_COUNTRY:eq:US", "FLOW:eq:EX", "HS_CHAPTER:eq:61"]}),
        
        # Transport modes
        ("Show sea imports from Japan in Q1 2026", {"intent": "summary", "trade_direction": "IM", "origin_country": "JP", "quarter": "Q1", "year": 2026, "mode_of_transport": "sea"}, {"dimensions": "FLOW", "period": "2026-Q1", "frequency": "Q", "filter": ["PARTNER_COUNTRY:eq:JP", "FLOW:eq:IM", "MODE_OF_TRANSPORT:eq:1"]}),
        ("Show the total value of sea cargo imports from Japan in Q1 2026", {"intent": "summary", "trade_direction": "IM", "origin_country": "JP", "quarter": "Q1", "year": 2026, "mode_of_transport": "sea"}, {"dimensions": "FLOW", "period": "2026-Q1", "frequency": "Q", "filter": ["PARTNER_COUNTRY:eq:JP", "FLOW:eq:IM", "MODE_OF_TRANSPORT:eq:1"]}),
        ("What is the total value of air freight exports to Germany in 2025?", {"intent": "summary", "trade_direction": "EX", "destination_country": "DE", "year": 2025, "mode_of_transport": "air"}, {"dimensions": "FLOW", "period": "2025", "filter": ["PARTNER_COUNTRY:eq:DE", "FLOW:eq:EX", "MODE_OF_TRANSPORT:eq:4"]}),
        
        # Relative date expressions (assuming current year is 2026)
        ("How much did Cambodia export in total last year?", {"intent": "summary", "trade_direction": "EX", "year": 2025}, {"dimensions": "FLOW", "period": "2025", "filter": ["FLOW:eq:EX"]}),
        ("Show total imports this year", {"intent": "summary", "trade_direction": "IM", "year": 2026}, {"dimensions": "FLOW", "period": "2026", "filter": ["FLOW:eq:IM"]}),
        
        # High-risk Direction & Country combinations
        ("imports from Japan", {"intent": "summary", "trade_direction": "IM", "origin_country": "JP"}, {"dimensions": "FLOW", "filter": ["PARTNER_COUNTRY:eq:JP", "FLOW:eq:IM"]}),
        ("exports to Japan", {"intent": "summary", "trade_direction": "EX", "destination_country": "JP"}, {"dimensions": "FLOW", "filter": ["PARTNER_COUNTRY:eq:JP", "FLOW:eq:EX"]}),
        
        # Ambiguous cases (Checking default behaviors)
        ("Rice exports", {"intent": "summary", "trade_direction": "EX", "hs_code": "1006"}, {"dimensions": "FLOW", "filter": ["FLOW:eq:EX", "HS_HEADING:eq:1006"]}, True, "default_year"),
        ("Trade with Japan", {"intent": "summary", "partner_country": "JP"}, {"dimensions": "FLOW", "filter": ["PARTNER_COUNTRY:eq:JP"]}, True, "default_year"),
        ("How much last year", {"intent": "summary", "year": 2025}, {"dimensions": "FLOW", "period": "2025"}, True, "default_flow"),
        ("Imports by sea", {"intent": "summary", "trade_direction": "IM", "mode_of_transport": "sea"}, {"dimensions": "FLOW", "filter": ["FLOW:eq:IM", "MODE_OF_TRANSPORT:eq:1"]}, True, "default_year"),
        ("Show total trade in 2025", {"intent": "summary", "year": 2025}, {"dimensions": "FLOW", "period": "2025"}, True, "default_flow"),
        
        # End-to-end examples
        ("What was Cambodia's rice export value in 2025?", {"intent": "summary", "trade_direction": "EX", "hs_code": "1006", "year": 2025}, {"dimensions": "FLOW", "period": "2025", "filter": ["FLOW:eq:EX", "HS_HEADING:eq:1006"]}, False, None, True, ["1006", "2025", "USD"]),
        ("Give me a summary of all imports in Q1 2026.", {"intent": "summary", "trade_direction": "IM", "quarter": "Q1", "year": 2026}, {"dimensions": "FLOW", "period": "2026-Q1", "frequency": "Q", "filter": ["FLOW:eq:IM"]}, False, None, True, ["import", "2026", "Q1"]),
        ("What was Cambodia's total export value last year?", {"intent": "summary", "trade_direction": "EX", "year": 2025}, {"dimensions": "FLOW", "period": "2025", "filter": ["FLOW:eq:EX"]}, False, None, True, ["export", "2025"])
    ]

    for q, ep, eu, *rest in summary_questions:
        ambig = rest[0] if len(rest) > 0 else False
        behavior = rest[1] if len(rest) > 1 else None
        e2e = rest[2] if len(rest) > 2 else False
        e2e_contains = rest[3] if len(rest) > 3 else None
        
        cases.append({
            "id": case_id,
            "question": q,
            "intent": "summary",
            "expected_params": ep,
            "expected_url_params": eu,
            "ambiguous": ambig,
            "expected_behavior": behavior,
            "e2e": e2e,
            "expected_answer_contains": e2e_contains
        })
        case_id += 1

    # 2. RANKING INTENT (22 cases)
    ranking_questions = [
        ("Top 10 export destinations in 2025.", {"intent": "ranking", "trade_direction": "EX", "year": 2025, "limit": 10, "sort_order": "desc"}, {"dimensions": "PARTNER_COUNTRY", "period": "2025", "limit": 10, "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:EX"]}),
        ("Which countries imported the most from Cambodia?", {"intent": "ranking", "trade_direction": "EX", "limit": 10, "sort_order": "desc"}, {"dimensions": "PARTNER_COUNTRY", "limit": 10, "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:EX"]}),
        ("Rank Cambodia's export partners by value.", {"intent": "ranking", "trade_direction": "EX", "sort_order": "desc"}, {"dimensions": "PARTNER_COUNTRY", "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:EX"]}),
        ("Who are Cambodia's top 5 trading partners by export value?", {"intent": "ranking", "trade_direction": "EX", "limit": 5, "sort_order": "desc"}, {"dimensions": "PARTNER_COUNTRY", "limit": 5, "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:EX"]}),
        ("Rank the top 10 HS chapters by import volume.", {"intent": "ranking", "trade_direction": "IM", "limit": 10, "sort_order": "desc", "group_by": ["hs_chapter"]}, {"dimensions": "HS_CHAPTER", "limit": 10, "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:IM"]}),
        ("Which partner countries import the most Cambodian rice?", {"intent": "ranking", "trade_direction": "EX", "hs_code": "1006", "sort_order": "desc"}, {"dimensions": "PARTNER_COUNTRY", "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:EX", "HS_HEADING:eq:1006"]}),
        ("Show me the bottom 20 partner countries by trade value.", {"intent": "ranking", "limit": 20, "sort_order": "asc"}, {"dimensions": "PARTNER_COUNTRY", "limit": 20, "sort": "VALUE_USD:asc"}),
        ("Top 5 destination countries for air exports in 2024", {"intent": "ranking", "trade_direction": "EX", "year": 2024, "limit": 5, "sort_order": "desc", "mode_of_transport": "air"}, {"dimensions": "PARTNER_COUNTRY", "period": "2024", "limit": 5, "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:EX", "MODE_OF_TRANSPORT:eq:4"]}),
        ("Which countries imported the largest volume of Cambodian garments (HS 61) by air?", {"intent": "ranking", "trade_direction": "EX", "hs_chapter": "61", "mode_of_transport": "air", "sort_order": "desc"}, {"dimensions": "PARTNER_COUNTRY", "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:EX", "HS_CHAPTER:eq:61", "MODE_OF_TRANSPORT:eq:4"]}),
        ("Rank top import origins in 2025", {"intent": "ranking", "trade_direction": "IM", "year": 2025, "sort_order": "desc"}, {"dimensions": "PARTNER_COUNTRY", "period": "2025", "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:IM"]}),
        ("Rank countries by trade value in 2025", {"intent": "ranking", "year": 2025, "sort_order": "desc"}, {"dimensions": "PARTNER_COUNTRY", "period": "2025", "sort": "VALUE_USD:desc"}),
        ("Show top countries", {"intent": "ranking", "sort_order": "desc"}, {"dimensions": "PARTNER_COUNTRY", "sort": "VALUE_USD:desc"}, True, "default_year_and_flow"),
        ("Rank exports by country", {"intent": "ranking", "trade_direction": "EX", "sort_order": "desc"}, {"dimensions": "PARTNER_COUNTRY", "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:EX"]}, True, "default_year"),
        
        # Variations for intent ranking
        ("Top partners for Cambodia imports", {"intent": "ranking", "trade_direction": "IM", "sort_order": "desc"}, {"dimensions": "PARTNER_COUNTRY", "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:IM"]}),
        ("Bottom 10 countries we imported goods from in 2025.", {"intent": "ranking", "trade_direction": "IM", "year": 2025, "limit": 10, "sort_order": "asc"}, {"dimensions": "PARTNER_COUNTRY", "period": "2025", "limit": 10, "sort": "VALUE_USD:asc", "filter": ["FLOW:eq:IM"]}),
        ("Rank the top 10 most exported HS codes to China.", {"intent": "ranking", "trade_direction": "EX", "destination_country": "CN", "limit": 10, "sort_order": "desc", "group_by": ["hs_code"]}, {"dimensions": "HS_CHAPTER", "limit": 10, "sort": "VALUE_USD:desc", "filter": ["PARTNER_COUNTRY:eq:CN", "FLOW:eq:EX"]}),
        ("Who are the top buyers of Cambodian rubber?", {"intent": "ranking", "trade_direction": "EX", "hs_code": "4001", "sort_order": "desc"}, {"dimensions": "PARTNER_COUNTRY", "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:EX", "HS_HEADING:eq:4001"]}),
        ("What are the top 5 imported products from Thailand?", {"intent": "ranking", "trade_direction": "IM", "origin_country": "TH", "limit": 5, "sort_order": "desc", "group_by": ["hs_code"]}, {"dimensions": "HS_CHAPTER", "limit": 5, "sort": "VALUE_USD:desc", "filter": ["PARTNER_COUNTRY:eq:TH", "FLOW:eq:IM"]}),
        ("Rank exports of rice by transport mode", {"intent": "ranking", "trade_direction": "EX", "hs_code": "1006", "sort_order": "desc", "group_by": ["mode_of_transport"]}, {"dimensions": "MODE_OF_TRANSPORT", "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:EX", "HS_HEADING:eq:1006"]}),
        ("Rank partner countries by weight", {"intent": "ranking", "sort_order": "desc", "sort_metric": "NET_WEIGHT"}, {"dimensions": "PARTNER_COUNTRY", "sort": "NET_WEIGHT:desc"}),
        
        # End to end
        ("Who are Cambodia's top 5 trading partners by export value?", {"intent": "ranking", "trade_direction": "EX", "limit": 5, "sort_order": "desc"}, {"dimensions": "PARTNER_COUNTRY", "limit": 5, "sort": "VALUE_USD:desc", "filter": ["FLOW:eq:EX"]}, False, None, True, ["top", "partner", "export"]),
        ("Show the bottom 10 countries we imported goods from in 2025.", {"intent": "ranking", "trade_direction": "IM", "year": 2025, "limit": 10, "sort_order": "asc"}, {"dimensions": "PARTNER_COUNTRY", "period": "2025", "limit": 10, "sort": "VALUE_USD:asc", "filter": ["FLOW:eq:IM"]}, False, None, True, ["bottom", "import", "2025"])
    ]

    for q, ep, eu, *rest in ranking_questions:
        ambig = rest[0] if len(rest) > 0 else False
        behavior = rest[1] if len(rest) > 1 else None
        e2e = rest[2] if len(rest) > 2 else False
        e2e_contains = rest[3] if len(rest) > 3 else None
        
        cases.append({
            "id": case_id,
            "question": q,
            "intent": "ranking",
            "expected_params": ep,
            "expected_url_params": eu,
            "ambiguous": ambig,
            "expected_behavior": behavior,
            "e2e": e2e,
            "expected_answer_contains": e2e_contains
        })
        case_id += 1

    # 3. TREND INTENT (22 cases)
    trend_questions = [
        ("Show exports from 2020 to 2025.", {"intent": "trend", "trade_direction": "EX", "start_period": "2020", "end_period": "2025"}, {"dimensions": "PERIOD,FLOW", "start-period": "2020", "end-period": "2025", "filter": ["FLOW:eq:EX"]}),
        ("How have imports changed over the last five years?", {"intent": "trend", "trade_direction": "IM", "start_period": "2022", "end_period": "2026"}, {"dimensions": "PERIOD,FLOW", "start-period": "2022", "end-period": "2026", "filter": ["FLOW:eq:IM"]}),
        ("How did exports to China trend over the last 3 years?", {"intent": "trend", "trade_direction": "EX", "destination_country": "CN", "start_period": "2024", "end_period": "2026"}, {"dimensions": "PERIOD,FLOW", "start-period": "2024", "end-period": "2026", "filter": ["PARTNER_COUNTRY:eq:CN", "FLOW:eq:EX"]}),
        ("Show me the monthly import trend for HS Code 8517 in 2025.", {"intent": "trend", "trade_direction": "IM", "hs_code": "8517", "year": 2025, "frequency": "M"}, {"dimensions": "PERIOD,FLOW", "period": "2025", "frequency": "M", "filter": ["FLOW:eq:IM", "HS_HEADING:eq:8517"]}),
        ("What is the quarterly trade balance trend for 2024?", {"intent": "trend", "year": 2024, "frequency": "Q"}, {"dimensions": "PERIOD,FLOW", "period": "2024", "frequency": "Q"}),
        ("Show monthly exports of rice in 2025", {"intent": "trend", "trade_direction": "EX", "hs_code": "1006", "year": 2025, "frequency": "M"}, {"dimensions": "PERIOD,FLOW", "period": "2025", "frequency": "M", "filter": ["FLOW:eq:EX", "HS_HEADING:eq:1006"]}),
        ("How have imports from Japan trended monthly?", {"intent": "trend", "trade_direction": "IM", "origin_country": "JP", "frequency": "M"}, {"dimensions": "PERIOD,FLOW", "frequency": "M", "filter": ["PARTNER_COUNTRY:eq:JP", "FLOW:eq:IM"]}),
        ("Show trend of trade value with Vietnam from 2021 to 2025", {"intent": "trend", "partner_country": "VN", "start_period": "2021", "end_period": "2025"}, {"dimensions": "PERIOD,FLOW", "start-period": "2021", "end-period": "2025", "filter": ["PARTNER_COUNTRY:eq:VN"]}),
        ("How did Cambodia's trade balance trend each month last year?", {"intent": "trend", "year": 2025, "frequency": "M"}, {"dimensions": "PERIOD,FLOW", "period": "2025", "frequency": "M"}),
        ("Trend of garment exports by air since 2023", {"intent": "trend", "trade_direction": "EX", "hs_chapter": "61", "mode_of_transport": "air", "start_period": "2023"}, {"dimensions": "PERIOD,FLOW", "start-period": "2023", "filter": ["FLOW:eq:EX", "HS_CHAPTER:eq:61", "MODE_OF_TRANSPORT:eq:4"]}),
        ("Quarterly import trend for cars", {"intent": "trend", "trade_direction": "IM", "hs_code": "8703", "frequency": "Q"}, {"dimensions": "PERIOD,FLOW", "frequency": "Q", "filter": ["FLOW:eq:IM", "HS_HEADING:eq:8703"]}),
        ("Monthly export trend", {"intent": "trend", "trade_direction": "EX", "frequency": "M"}, {"dimensions": "PERIOD,FLOW", "frequency": "M", "filter": ["FLOW:eq:EX"]}, True, "default_year"),
        ("Trade trend last 3 years", {"intent": "trend", "start_period": "2024", "end_period": "2026"}, {"dimensions": "PERIOD,FLOW", "start-period": "2024", "end-period": "2026"}, True, "default_flow"),
        
        # Variations
        ("Show the import trend over the last 5 years.", {"intent": "trend", "trade_direction": "IM", "start_period": "2022", "end_period": "2026"}, {"dimensions": "PERIOD,FLOW", "start-period": "2022", "end-period": "2026", "filter": ["FLOW:eq:IM"]}),
        ("How did Cambodia's exports to China trend over the last 3 years?", {"intent": "trend", "trade_direction": "EX", "destination_country": "CN", "start_period": "2024", "end_period": "2026"}, {"dimensions": "PERIOD,FLOW", "start-period": "2024", "end-period": "2026", "filter": ["PARTNER_COUNTRY:eq:CN", "FLOW:eq:EX"]}),
        ("Show me the monthly import trend for HS Code 8517 in 2025.", {"intent": "trend", "trade_direction": "IM", "hs_code": "8517", "year": 2025, "frequency": "M"}, {"dimensions": "PERIOD,FLOW", "period": "2025", "frequency": "M", "filter": ["FLOW:eq:IM", "HS_HEADING:eq:8517"]}),
        ("Monthly export value for rice in 2024", {"intent": "trend", "trade_direction": "EX", "hs_code": "1006", "year": 2024, "frequency": "M"}, {"dimensions": "PERIOD,FLOW", "period": "2024", "frequency": "M", "filter": ["FLOW:eq:EX", "HS_HEADING:eq:1006"]}),
        ("Quarterly trade balance trend for 2024", {"intent": "trend", "year": 2024, "frequency": "Q"}, {"dimensions": "PERIOD,FLOW", "period": "2024", "frequency": "Q"}),
        ("How did Cambodia's trade balance trend each month last year?", {"intent": "trend", "year": 2025, "frequency": "M"}, {"dimensions": "PERIOD,FLOW", "period": "2025", "frequency": "M"}),
        ("Exports trend over time", {"intent": "trend", "trade_direction": "EX"}, {"dimensions": "PERIOD,FLOW", "filter": ["FLOW:eq:EX"]}, True, "default_period"),
        
        # End to end
        ("How have Cambodia's exports to China trended over the last 3 years?", {"intent": "trend", "trade_direction": "EX", "destination_country": "CN", "start_period": "2024", "end_period": "2026"}, {"dimensions": "PERIOD,FLOW", "start-period": "2024", "end-period": "2026", "filter": ["PARTNER_COUNTRY:eq:CN", "FLOW:eq:EX"]}, False, None, True, ["export", "trend", "China"]),
        ("Show me the monthly import trend for HS Code 8517 in 2025.", {"intent": "trend", "trade_direction": "IM", "hs_code": "8517", "year": 2025, "frequency": "M"}, {"dimensions": "PERIOD,FLOW", "period": "2025", "frequency": "M", "filter": ["FLOW:eq:IM", "HS_HEADING:eq:8517"]}, False, None, True, ["import", "monthly", "2025"])
    ]

    for q, ep, eu, *rest in trend_questions:
        ambig = rest[0] if len(rest) > 0 else False
        behavior = rest[1] if len(rest) > 1 else None
        e2e = rest[2] if len(rest) > 2 else False
        e2e_contains = rest[3] if len(rest) > 3 else None
        
        cases.append({
            "id": case_id,
            "question": q,
            "intent": "trend",
            "expected_params": ep,
            "expected_url_params": eu,
            "ambiguous": ambig,
            "expected_behavior": behavior,
            "e2e": e2e,
            "expected_answer_contains": e2e_contains
        })
        case_id += 1

    # 4. COMPARISON INTENT (22 cases)
    comparison_questions = [
        ("Compare exports to Japan and China.", {"intent": "comparison", "trade_direction": "EX", "partner_countries": ["JP", "CN"]}, {"dimensions": "PARTNER_COUNTRY,FLOW", "filter": ["PARTNER_COUNTRY:in:JP,CN", "FLOW:eq:EX"]}),
        ("Compare imports in 2024 vs 2025.", {"intent": "comparison", "trade_direction": "IM", "years": [2024, 2025]}, {"dimensions": "PARTNER_COUNTRY,FLOW", "start_period": "2024", "end_period": "2025", "filter": ["FLOW:eq:IM"]}),
        ("Compare Cambodia's exports to the USA vs exports to Germany in 2025.", {"intent": "comparison", "trade_direction": "EX", "partner_countries": ["US", "DE"], "year": 2025}, {"dimensions": "PARTNER_COUNTRY,FLOW", "period": "2025", "filter": ["PARTNER_COUNTRY:in:US,DE", "FLOW:eq:EX"]}),
        ("Show me a side-by-side comparison of import values for HS Chapter 84 vs HS Chapter 85.", {"intent": "comparison", "trade_direction": "IM", "hs_chapters": ["84", "85"]}, {"dimensions": "PARTNER_COUNTRY,FLOW", "filter": ["FLOW:eq:IM", "HS_CHAPTER:in:84,85"]}),
        ("Compare Q1 2025 trade performance against Q1 2024.", {"intent": "comparison", "quarters": ["2024-Q1", "2025-Q1"]}, {"dimensions": "PARTNER_COUNTRY,FLOW"}),
        ("Compare air freight exports to Japan against sea freight exports to Japan.", {"intent": "comparison", "trade_direction": "EX", "partner_country": "JP", "mode_of_transport": "air"}, {"dimensions": "PARTNER_COUNTRY,FLOW", "filter": ["PARTNER_COUNTRY:eq:JP", "FLOW:eq:EX", "MODE_OF_TRANSPORT:eq:4"]}),
        ("Compare exports to US and China in 2024", {"intent": "comparison", "trade_direction": "EX", "partner_countries": ["US", "CN"], "year": 2024}, {"dimensions": "PARTNER_COUNTRY,FLOW", "period": "2024", "filter": ["PARTNER_COUNTRY:in:US,CN", "FLOW:eq:EX"]}),
        ("Compare imports of rice and wheat in 2025", {"intent": "comparison", "trade_direction": "IM", "hs_codes": ["1006", "1001"], "year": 2025}, {"dimensions": "PARTNER_COUNTRY,FLOW", "period": "2025", "filter": ["FLOW:eq:IM", "HS_HEADING:in:1006,1001"]}),
        ("Compare Cambodia exports to ASEAN vs EU", {"intent": "comparison", "trade_direction": "EX"}, {"dimensions": "PARTNER_COUNTRY,FLOW", "filter": ["FLOW:eq:EX"]}),
        ("Compare trade with Vietnam and Thailand", {"intent": "comparison", "partner_countries": ["VN", "TH"]}, {"dimensions": "PARTNER_COUNTRY,FLOW", "filter": ["PARTNER_COUNTRY:in:VN,TH"]}),
        ("Compare imports by sea vs imports by air", {"intent": "comparison", "trade_direction": "IM", "mode_of_transport": "sea"}, {"dimensions": "PARTNER_COUNTRY,FLOW", "filter": ["FLOW:eq:IM", "MODE_OF_TRANSPORT:eq:1"]}),
        ("Compare trade", {"intent": "comparison"}, {"dimensions": "PARTNER_COUNTRY,FLOW"}, True, "default_year_and_flow_and_partners"),
        ("Compare exports to Japan vs exports to Korea", {"intent": "comparison", "trade_direction": "EX", "partner_countries": ["JP", "KR"]}, {"dimensions": "PARTNER_COUNTRY,FLOW", "filter": ["PARTNER_COUNTRY:in:JP,KR", "FLOW:eq:EX"]}, True, "default_year"),
        
        # Variations
        ("Compare Cambodia's exports to the US versus exports to China in 2024.", {"intent": "comparison", "trade_direction": "EX", "partner_countries": ["US", "CN"], "year": 2024}, {"dimensions": "PARTNER_COUNTRY,FLOW", "period": "2024", "filter": ["PARTNER_COUNTRY:in:US,CN", "FLOW:eq:EX"]}),
        ("Show me a side-by-side comparison of import values for HS Chapter 84 vs HS Chapter 85.", {"intent": "comparison", "trade_direction": "IM", "hs_chapters": ["84", "85"]}, {"dimensions": "PARTNER_COUNTRY,FLOW", "filter": ["FLOW:eq:IM", "HS_CHAPTER:in:84,85"]}),
        ("Compare Q1 2025 trade performance against Q1 2024.", {"intent": "comparison", "quarters": ["2024-Q1", "2025-Q1"]}, {"dimensions": "PARTNER_COUNTRY,FLOW"}),
        ("Compare air freight exports to Japan against sea freight exports to Japan.", {"intent": "comparison", "trade_direction": "EX", "partner_country": "JP", "mode_of_transport": "air"}, {"dimensions": "PARTNER_COUNTRY,FLOW", "filter": ["PARTNER_COUNTRY:eq:JP", "FLOW:eq:EX", "MODE_OF_TRANSPORT:eq:4"]}),
        ("Compare imports from Thailand vs imports from Vietnam in 2025.", {"intent": "comparison", "trade_direction": "IM", "partner_countries": ["TH", "VN"], "year": 2025}, {"dimensions": "PARTNER_COUNTRY,FLOW", "period": "2025", "filter": ["PARTNER_COUNTRY:in:TH,VN", "FLOW:eq:IM"]}),
        ("Compare exports to China in 2024 and 2025", {"intent": "comparison", "trade_direction": "EX", "destination_country": "CN", "years": [2024, 2025]}, {"dimensions": "PARTNER_COUNTRY,FLOW", "start_period": "2024", "end_period": "2025", "filter": ["PARTNER_COUNTRY:eq:CN", "FLOW:eq:EX"]}),
        ("Compare rice exports by air vs sea", {"intent": "comparison", "trade_direction": "EX", "hs_code": "1006", "mode_of_transport": "air"}, {"dimensions": "PARTNER_COUNTRY,FLOW", "filter": ["FLOW:eq:EX", "HS_HEADING:eq:1006", "MODE_OF_TRANSPORT:eq:4"]}),
        
        # End to end
        ("Compare Cambodia's exports to the US versus exports to China in 2024.", {"intent": "comparison", "trade_direction": "EX", "partner_countries": ["US", "CN"], "year": 2024}, {"dimensions": "PARTNER_COUNTRY,FLOW", "period": "2024", "filter": ["PARTNER_COUNTRY:in:US,CN", "FLOW:eq:EX"]}, False, None, True, ["compare", "US", "China", "2024"]),
        ("Compare imports from Thailand vs imports from Vietnam in 2025.", {"intent": "comparison", "trade_direction": "IM", "partner_countries": ["TH", "VN"], "year": 2025}, {"dimensions": "PARTNER_COUNTRY,FLOW", "period": "2025", "filter": ["PARTNER_COUNTRY:in:TH,VN", "FLOW:eq:IM"]}, False, None, True, ["compare", "Thailand", "Vietnam", "2025"])
    ]

    for q, ep, eu, *rest in comparison_questions:
        ambig = rest[0] if len(rest) > 0 else False
        behavior = rest[1] if len(rest) > 1 else None
        e2e = rest[2] if len(rest) > 2 else False
        e2e_contains = rest[3] if len(rest) > 3 else None
        
        cases.append({
            "id": case_id,
            "question": q,
            "intent": "comparison",
            "expected_params": ep,
            "expected_url_params": eu,
            "ambiguous": ambig,
            "expected_behavior": behavior,
            "e2e": e2e,
            "expected_answer_contains": e2e_contains
        })
        case_id += 1

    # 5. BREAKDOWN INTENT (22 cases)
    breakdown_questions = [
        ("Break down exports by transport mode.", {"intent": "breakdown", "trade_direction": "EX", "group_by": ["mode_of_transport"]}, {"dimensions": "MODE_OF_TRANSPORT", "filter": ["FLOW:eq:EX"]}),
        ("Show export composition by product.", {"intent": "breakdown", "trade_direction": "EX", "group_by": ["hs_code"]}, {"dimensions": "HS_CHAPTER", "filter": ["FLOW:eq:EX"]}),
        ("Break down Cambodia's total exports by HS Chapter for 2025.", {"intent": "breakdown", "trade_direction": "EX", "year": 2025, "group_by": ["hs_chapter"]}, {"dimensions": "HS_CHAPTER", "period": "2025", "filter": ["FLOW:eq:EX"]}),
        ("Show me the breakdown of imports by mode of transport.", {"intent": "breakdown", "trade_direction": "IM", "group_by": ["mode_of_transport"]}, {"dimensions": "MODE_OF_TRANSPORT", "filter": ["FLOW:eq:IM"]}),
        ("Divide Cambodia's trade with ASEAN partners by HS Heading.", {"intent": "breakdown", "group_by": ["hs_heading"]}, {"dimensions": "HS_CHAPTER"}),
        ("Create a pie chart showing the breakdown of 2024 agricultural exports.", {"intent": "breakdown", "trade_direction": "EX", "year": 2024, "group_by": ["hs_chapter"]}, {"dimensions": "HS_CHAPTER", "period": "2024", "filter": ["FLOW:eq:EX"]}),
        ("Break down imports from China by HS code in 2025", {"intent": "breakdown", "trade_direction": "IM", "origin_country": "CN", "year": 2025, "group_by": ["hs_code"]}, {"dimensions": "HS_CHAPTER", "period": "2025", "filter": ["PARTNER_COUNTRY:eq:CN", "FLOW:eq:IM"]}),
        ("Break down exports to Japan by transport mode", {"intent": "breakdown", "trade_direction": "EX", "destination_country": "JP", "group_by": ["mode_of_transport"]}, {"dimensions": "MODE_OF_TRANSPORT", "filter": ["PARTNER_COUNTRY:eq:JP", "FLOW:eq:EX"]}),
        ("Divide Cambodia's total trade last year by partner country.", {"intent": "breakdown", "year": 2025, "group_by": ["partner_country"]}, {"dimensions": "PARTNER_COUNTRY", "period": "2025"}),
        ("Break down rice exports by country", {"intent": "breakdown", "trade_direction": "EX", "hs_code": "1006", "group_by": ["partner_country"]}, {"dimensions": "PARTNER_COUNTRY", "filter": ["FLOW:eq:EX", "HS_HEADING:eq:1006"]}),
        ("Breakdown of imports by country of origin in 2025", {"intent": "breakdown", "trade_direction": "IM", "year": 2025, "group_by": ["partner_country"]}, {"dimensions": "PARTNER_COUNTRY", "period": "2025", "filter": ["FLOW:eq:IM"]}),
        ("Breakdown exports", {"intent": "breakdown", "trade_direction": "EX"}, {"dimensions": "HS_CHAPTER", "filter": ["FLOW:eq:EX"]}, True, "default_group_by_and_year"),
        ("Show breakdown by transport", {"intent": "breakdown", "group_by": ["mode_of_transport"]}, {"dimensions": "MODE_OF_TRANSPORT"}, True, "default_year_and_flow"),
        
        # Variations
        ("Break down Cambodia's total exports by HS Chapter for 2025.", {"intent": "breakdown", "trade_direction": "EX", "year": 2025, "group_by": ["hs_chapter"]}, {"dimensions": "HS_CHAPTER", "period": "2025", "filter": ["FLOW:eq:EX"]}),
        ("Show me the breakdown of imports by mode of transport.", {"intent": "breakdown", "trade_direction": "IM", "group_by": ["mode_of_transport"]}, {"dimensions": "MODE_OF_TRANSPORT", "filter": ["FLOW:eq:IM"]}),
        ("Divide Cambodia's total trade last year by partner country.", {"intent": "breakdown", "year": 2025, "group_by": ["partner_country"]}, {"dimensions": "PARTNER_COUNTRY", "period": "2025"}),
        ("Create a pie chart showing the breakdown of 2024 agricultural exports.", {"intent": "breakdown", "trade_direction": "EX", "year": 2024, "group_by": ["hs_chapter"]}, {"dimensions": "HS_CHAPTER", "period": "2024", "filter": ["FLOW:eq:EX"]}),
        ("Breakdown of 2025 imports from Thailand by product.", {"intent": "breakdown", "trade_direction": "IM", "origin_country": "TH", "year": 2025, "group_by": ["hs_code"]}, {"dimensions": "HS_CHAPTER", "period": "2025", "filter": ["PARTNER_COUNTRY:eq:TH", "FLOW:eq:IM"]}),
        ("Show the transport mode breakdown for electronics exports to the US.", {"intent": "breakdown", "trade_direction": "EX", "destination_country": "US", "hs_code": "8517", "group_by": ["mode_of_transport"]}, {"dimensions": "MODE_OF_TRANSPORT", "filter": ["PARTNER_COUNTRY:eq:US", "FLOW:eq:EX", "HS_HEADING:eq:8517"]}),
        ("Breakdown total trade by direction in 2025", {"intent": "breakdown", "year": 2025, "group_by": ["flow"]}, {"dimensions": "FLOW", "period": "2025"}),
        
        # End to end
        ("Break down Cambodia's total exports by HS Chapter for 2025.", {"intent": "breakdown", "trade_direction": "EX", "year": 2025, "group_by": ["hs_chapter"]}, {"dimensions": "HS_CHAPTER", "period": "2025", "filter": ["FLOW:eq:EX"]}, False, None, True, ["breakdown", "export", "2025"]),
        ("Show me the breakdown of imports by mode of transport.", {"intent": "breakdown", "trade_direction": "IM", "group_by": ["mode_of_transport"]}, {"dimensions": "MODE_OF_TRANSPORT", "filter": ["FLOW:eq:IM"]}, False, None, True, ["breakdown", "import", "transport"])
    ]

    for q, ep, eu, *rest in breakdown_questions:
        ambig = rest[0] if len(rest) > 0 else False
        behavior = rest[1] if len(rest) > 1 else None
        e2e = rest[2] if len(rest) > 2 else False
        e2e_contains = rest[3] if len(rest) > 3 else None
        
        cases.append({
            "id": case_id,
            "question": q,
            "intent": "breakdown",
            "expected_params": ep,
            "expected_url_params": eu,
            "ambiguous": ambig,
            "expected_behavior": behavior,
            "e2e": e2e,
            "expected_answer_contains": e2e_contains
        })
        case_id += 1

    # 6. GROWTH INTENT (22 cases)
    growth_questions = [
        ("What was export growth from 2024 to 2025?", {"intent": "growth", "trade_direction": "EX", "years": [2024, 2025]}, {"dimensions": "PARTNER_COUNTRY", "start_period": "2024", "end_period": "2025", "filter": ["FLOW:eq:EX"]}),
        ("Which products grew the fastest?", {"intent": "growth", "group_by": ["hs_code"]}, {"dimensions": "PARTNER_COUNTRY"}),
        ("What is the year-over-year growth of exports to Vietnam?", {"intent": "growth", "trade_direction": "EX", "destination_country": "VN"}, {"dimensions": "PARTNER_COUNTRY", "filter": ["PARTNER_COUNTRY:eq:VN", "FLOW:eq:EX"]}),
        ("Show me the growth rate for HS Code 6109 imports from 2024 to 2025.", {"intent": "growth", "trade_direction": "IM", "hs_code": "6109", "years": [2024, 2025]}, {"dimensions": "PARTNER_COUNTRY", "start_period": "2024", "end_period": "2025", "filter": ["FLOW:eq:IM", "HS_CODE:eq:6109"]}),
        ("Which partner countries showed the highest growth in trade value this quarter?", {"intent": "growth", "frequency": "Q"}, {"dimensions": "PARTNER_COUNTRY", "frequency": "Q"}),
        ("What is the import growth rate from Thailand in 2025?", {"intent": "growth", "trade_direction": "IM", "origin_country": "TH", "year": 2025}, {"dimensions": "PARTNER_COUNTRY", "period": "2025", "filter": ["PARTNER_COUNTRY:eq:TH", "FLOW:eq:IM"]}),
        ("Which HS chapters had the highest export growth in 2025?", {"intent": "growth", "trade_direction": "EX", "year": 2025, "group_by": ["hs_chapter"]}, {"dimensions": "PARTNER_COUNTRY", "period": "2025", "filter": ["FLOW:eq:EX"]}),
        ("What is the YoY export growth of garments?", {"intent": "growth", "trade_direction": "EX", "hs_chapter": "61"}, {"dimensions": "PARTNER_COUNTRY", "filter": ["FLOW:eq:EX", "HS_CHAPTER:eq:61"]}),
        ("Show me import growth from China over the last 3 years", {"intent": "growth", "trade_direction": "IM", "origin_country": "CN", "start_period": "2024", "end_period": "2026"}, {"dimensions": "PARTNER_COUNTRY", "start_period": "2024", "end_period": "2026", "filter": ["PARTNER_COUNTRY:eq:CN", "FLOW:eq:IM"]}),
        ("Which transport modes had the fastest import growth in 2025?", {"intent": "growth", "trade_direction": "IM", "year": 2025, "group_by": ["mode_of_transport"]}, {"dimensions": "PARTNER_COUNTRY", "period": "2025", "filter": ["FLOW:eq:IM"]}),
        ("Show product growth rates in 2025", {"intent": "growth", "year": 2025, "group_by": ["hs_code"]}, {"dimensions": "PARTNER_COUNTRY", "period": "2025"}),
        ("Measure growth", {"intent": "growth"}, {"dimensions": "PARTNER_COUNTRY"}, True, "default_year_and_flow"),
        ("Show growth for exports to US", {"intent": "growth", "trade_direction": "EX", "destination_country": "US"}, {"dimensions": "PARTNER_COUNTRY", "filter": ["PARTNER_COUNTRY:eq:US", "FLOW:eq:EX"]}, True, "default_year"),
        
        # Variations
        ("Which partner country had the highest export growth rate last year?", {"intent": "growth", "trade_direction": "EX", "year": 2025}, {"dimensions": "PARTNER_COUNTRY", "period": "2025", "filter": ["FLOW:eq:EX"]}),
        ("What was the year-over-year import growth rate for cars (HS 8703)?", {"intent": "growth", "trade_direction": "IM", "hs_code": "8703"}, {"dimensions": "PARTNER_COUNTRY", "filter": ["FLOW:eq:IM", "HS_HEADING:eq:8703"]}),
        ("Which HS chapters saw the largest decline in export value in 2025?", {"intent": "growth", "trade_direction": "EX", "year": 2025, "group_by": ["hs_chapter"]}, {"dimensions": "PARTNER_COUNTRY", "period": "2025", "filter": ["FLOW:eq:EX"]}),
        ("What was the month-over-month growth of imports from Vietnam this year?", {"intent": "growth", "trade_direction": "IM", "origin_country": "VN", "year": 2026, "frequency": "M"}, {"dimensions": "PARTNER_COUNTRY", "period": "2026", "frequency": "M", "filter": ["PARTNER_COUNTRY:eq:VN", "FLOW:eq:IM"]}),
        ("Which country has the fastest growing exports to Cambodia?", {"intent": "growth", "trade_direction": "IM"}, {"dimensions": "PARTNER_COUNTRY", "filter": ["FLOW:eq:IM"]}),
        ("Identify top 5 growth markets for rice exports.", {"intent": "growth", "trade_direction": "EX", "hs_code": "1006", "limit": 5}, {"dimensions": "PARTNER_COUNTRY", "limit": 5, "filter": ["FLOW:eq:EX", "HS_HEADING:eq:1006"]}),
        ("Compute quarterly export growth to Japan in 2025", {"intent": "growth", "trade_direction": "EX", "destination_country": "JP", "year": 2025, "frequency": "Q"}, {"dimensions": "PARTNER_COUNTRY", "period": "2025", "frequency": "Q", "filter": ["PARTNER_COUNTRY:eq:JP", "FLOW:eq:EX"]}),
        
        # End to end
        ("What is the year-over-year growth of exports to Vietnam?", {"intent": "growth", "trade_direction": "EX", "destination_country": "VN"}, {"dimensions": "PARTNER_COUNTRY", "filter": ["PARTNER_COUNTRY:eq:VN", "FLOW:eq:EX"]}, False, None, True, ["growth", "export", "Vietnam"]),
        ("Show me the growth rate for HS Code 6109 imports from 2024 to 2025.", {"intent": "growth", "trade_direction": "IM", "hs_code": "6109", "years": [2024, 2025]}, {"dimensions": "PARTNER_COUNTRY", "start_period": "2024", "end_period": "2025", "filter": ["FLOW:eq:IM", "HS_CODE:eq:6109"]}, False, None, True, ["growth", "import", "6109"])
    ]

    for q, ep, eu, *rest in growth_questions:
        ambig = rest[0] if len(rest) > 0 else False
        behavior = rest[1] if len(rest) > 1 else None
        e2e = rest[2] if len(rest) > 2 else False
        e2e_contains = rest[3] if len(rest) > 3 else None
        
        cases.append({
            "id": case_id,
            "question": q,
            "intent": "growth",
            "expected_params": ep,
            "expected_url_params": eu,
            "ambiguous": ambig,
            "expected_behavior": behavior,
            "e2e": e2e,
            "expected_answer_contains": e2e_contains
        })
        case_id += 1

    # 7. TRADE BALANCE INTENT (22 cases)
    balance_questions = [
        ("What was Cambodia's trade balance in 2025?", {"intent": "trade_balance", "year": 2025}, {"dimensions": "FLOW", "period": "2025"}),
        ("Show trade balance from 2020–2025.", {"intent": "trade_balance", "start_period": "2020", "end_period": "2025"}, {"dimensions": "FLOW", "start-period": "2020", "end-period": "2025"}),
        ("What is Cambodia's trade balance with the EU?", {"intent": "trade_balance", "partner_country": "EU"}, {"dimensions": "FLOW", "filter": ["PARTNER_COUNTRY:eq:EU"]}),
        ("Show me the export vs import surplus for HS Chapter 62.", {"intent": "trade_balance", "hs_chapter": "62"}, {"dimensions": "FLOW", "filter": ["HS_CHAPTER:eq:62"]}),
        ("Which partner countries do we have a trade deficit with?", {"intent": "trade_balance"}, {"dimensions": "FLOW"}),
        ("What is Cambodia's trade balance with Thailand?", {"intent": "trade_balance", "partner_country": "TH"}, {"dimensions": "FLOW", "filter": ["PARTNER_COUNTRY:eq:TH"]}),
        ("Show the export vs import surplus for HS Chapter 64 (footwear).", {"intent": "trade_balance", "hs_chapter": "64"}, {"dimensions": "FLOW", "filter": ["HS_CHAPTER:eq:64"]}),
        ("Which countries does Cambodia run a trade deficit with?", {"intent": "trade_balance"}, {"dimensions": "FLOW"}),
        ("Show the monthly trade balance surplus with the USA in 2025.", {"intent": "trade_balance", "partner_country": "US", "year": 2025, "frequency": "M"}, {"dimensions": "FLOW", "period": "2025", "frequency": "M", "filter": ["PARTNER_COUNTRY:eq:US"]}),
        ("What is the trade balance with China in 2025 by sea?", {"intent": "trade_balance", "partner_country": "CN", "year": 2025, "mode_of_transport": "sea"}, {"dimensions": "FLOW", "period": "2025", "filter": ["PARTNER_COUNTRY:eq:CN", "MODE_OF_TRANSPORT:eq:sea"]}),
        ("Quarterly trade balance with Vietnam", {"intent": "trade_balance", "partner_country": "VN", "frequency": "Q"}, {"dimensions": "FLOW", "frequency": "Q", "filter": ["PARTNER_COUNTRY:eq:VN"]}),
        ("Show trade balance", {"intent": "trade_balance"}, {"dimensions": "FLOW"}, True, "default_year_and_partner"),
        ("Trade balance with Japan", {"intent": "trade_balance", "partner_country": "JP"}, {"dimensions": "FLOW", "filter": ["PARTNER_COUNTRY:eq:JP"]}, True, "default_year"),
        
        # Variations
        ("What is Cambodia's trade balance with the EU?", {"intent": "trade_balance", "partner_country": "EU"}, {"dimensions": "FLOW", "filter": ["PARTNER_COUNTRY:eq:EU"]}),
        ("Show me the export vs import surplus for HS Chapter 62.", {"intent": "trade_balance", "hs_chapter": "62"}, {"dimensions": "FLOW", "filter": ["HS_CHAPTER:eq:62"]}),
        ("Which partner countries do we have a trade deficit with?", {"intent": "trade_balance"}, {"dimensions": "FLOW"}),
        ("What is Cambodia's trade balance with Thailand?", {"intent": "trade_balance", "partner_country": "TH"}, {"dimensions": "FLOW", "filter": ["PARTNER_COUNTRY:eq:TH"]}),
        ("Show the export vs import surplus for HS Chapter 64 (footwear).", {"intent": "trade_balance", "hs_chapter": "64"}, {"dimensions": "FLOW", "filter": ["HS_CHAPTER:eq:64"]}),
        ("Which countries does Cambodia run a trade deficit with?", {"intent": "trade_balance"}, {"dimensions": "FLOW"}),
        ("Show the monthly trade balance surplus with the USA in 2025.", {"intent": "trade_balance", "partner_country": "US", "year": 2025, "frequency": "M"}, {"dimensions": "FLOW", "period": "2025", "frequency": "M", "filter": ["PARTNER_COUNTRY:eq:US"]}),
        
        # End to end
        ("What is Cambodia's trade balance with Thailand?", {"intent": "trade_balance", "partner_country": "TH"}, {"dimensions": "FLOW", "filter": ["PARTNER_COUNTRY:eq:TH"]}, False, None, True, ["trade balance", "Thailand"]),
        ("Show the export vs import surplus for HS Chapter 64 (footwear).", {"intent": "trade_balance", "hs_chapter": "64"}, {"dimensions": "FLOW", "filter": ["HS_CHAPTER:eq:64"]}, False, None, True, ["surplus", "64", "footwear"])
    ]

    for q, ep, eu, *rest in balance_questions:
        ambig = rest[0] if len(rest) > 0 else False
        behavior = rest[1] if len(rest) > 1 else None
        e2e = rest[2] if len(rest) > 2 else False
        e2e_contains = rest[3] if len(rest) > 3 else None
        
        cases.append({
            "id": case_id,
            "question": q,
            "intent": "trade_balance",
            "expected_params": ep,
            "expected_url_params": eu,
            "ambiguous": ambig,
            "expected_behavior": behavior,
            "e2e": e2e,
            "expected_answer_contains": e2e_contains
        })
        case_id += 1

    # Save to JSON
    output_path = Path(__file__).parent / "accuracy_test_cases.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)
    
    print(f"Generated {len(cases)} test cases in {output_path}")

if __name__ == "__main__":
    generate_all_cases()
