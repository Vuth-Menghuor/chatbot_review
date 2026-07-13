"""NLG fallback template for growth intent."""

from typing import Any, Dict

from app.ai.nlg.format_utils import format_metric


def render_growth(
    facts: Dict[str, Any],
    flow_phrase: str,
    prod_phrase: str,
    trans_phrase: str,
    metrics: list,
) -> str:
    """Render growth fallback text."""
    data_quality = facts.get("data_quality") or {}
    growth_valid = data_quality.get("growth_valid", False)
    execution_mode = facts.get("execution_mode", "growth")
    directional_context = facts.get("directional_context") or facts.get("extra", {}).get("directional_context")

    # Degraded fallback:
    if not growth_valid or execution_mode != "growth":
        downgrade_reason = facts.get("growth_downgrade_reason", "Baseline period data was not available.")
        val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
        val_str = format_metric(val_usd, metrics) if val_usd else "unavailable"
        return (
            f"Growth rate could not be computed for Cambodia's {flow_phrase.strip()}{prod_phrase}{trans_phrase}: "
            f"{downgrade_reason} "
            f"The most recent available value was {val_str}."
        )

    records = facts.get("growth_records") or []

    # 1. Identify the entity grouping key
    entity_key = None
    if records:
        for key in ["PARTNER_COUNTRY", "partner_country", "HS_HEADING", "hs_heading",
                    "SITC_DIVISION", "sitc_division", "MODE_OF_TRANSPORT", "mode_of_transport",
                    "HS_CHAPTER", "hs_chapter", "FLOW", "flow"]:
            if key in records[0]:
                entity_key = key
                break

    # 2. Group records by entity
    entity_groups = {}
    if entity_key:
        for r in records:
            ent = r.get(entity_key)
            if ent is not None:
                entity_groups.setdefault(ent, []).append(r)
    else:
        entity_groups["Cambodia"] = records

    # 3. Find latest rows and new entrants
    latest_rows = []
    new_entrants = []
    for ent, ent_records in entity_groups.items():
        ent_records.sort(key=lambda x: str(x.get("period", "")))
        lat_r = next((r for r in reversed(ent_records) if r.get("growth_rate_pct") is not None), None)
        if lat_r:
            latest_rows.append(lat_r)
        else:
            new_entrants.append(str(ent))

    # Sort latest_rows according to Rule 3
    question_lower = facts.get("question", "").lower()
    is_fastest = any(kw in question_lower for kw in ["fastest", "rapid", "highest growth", "most growth"])

    if is_fastest:
        latest_rows.sort(key=lambda x: abs(x.get("growth_rate_pct") or 0.0), reverse=True)
    else:
        latest_rows.sort(key=lambda x: x.get("trade_value_usd", 0.0), reverse=True)

    all_periods = sorted(list(set(str(r.get("period")) for r in records if r.get("period"))))

    # 5. Output generation
    # Single-entity path
    if len(entity_groups) <= 1 or len(latest_rows) <= 1:
        if not latest_rows:
            return "No growth records with baseline data were found."

        latest = latest_rows[0]
        ent = latest.get(entity_key) if entity_key else None
        ent_recs = sorted(entity_groups[ent] if ent else records, key=lambda x: str(x.get("period", "")))

        rate = latest.get("growth_rate_pct")
        val_latest_str = format_metric(latest.get("trade_value_usd", 0.0), metrics)
        val_start_str = format_metric(ent_recs[0].get("trade_value_usd", 0.0), metrics)

        # Directional template
        flow_lc = flow_phrase.strip().lower()
        if directional_context == "decline":
            if rate is not None and rate < 0:
                return f"Yes, {flow_lc}{prod_phrase}{trans_phrase} declined by {abs(rate):.2f}% from {val_start_str} to {val_latest_str}."
            elif rate is not None:
                return f"No, {flow_lc}{prod_phrase}{trans_phrase} actually increased by {rate:.2f}%, not declined."

        # 3-period single-entity template
        if len(all_periods) >= 3:
            steps = []
            for i in range(1, len(ent_recs)):
                curr = ent_recs[i]
                r = curr.get("growth_rate_pct")
                if r is not None:
                    status = "grew" if r >= 0 else "declined"
                    steps.append(f"{status} {abs(r):.2f}% in {curr.get('period')}")
            steps_phrase = ", then ".join(steps)
            return f"Cambodia's {flow_phrase.strip()}{prod_phrase}{trans_phrase} {steps_phrase} (from {val_start_str} to {val_latest_str})."

        # 2-period single-entity template
        year1 = ent_recs[0].get("period", "")
        year2 = latest.get("period", "")
        status_word = "grew" if rate >= 0 else "declined"
        return f"Cambodia's {flow_phrase.strip()}{prod_phrase}{trans_phrase} {status_word} from {val_start_str} in {year1} to {val_latest_str} in {year2}, a growth rate of {rate:+.2f}%."

    # Multi-entity path
    else:
        start_year = all_periods[0] if all_periods else ""
        end_year = all_periods[-1] if all_periods else ""

        header = f"From {start_year} to {end_year}, Cambodia's {flow_phrase.strip()}{prod_phrase}{trans_phrase} grew across top partners:"
        if "import" in flow_phrase.lower():
            header = f"From {start_year} to {end_year}, Cambodia's {flow_phrase.strip()}{prod_phrase}{trans_phrase} grew across top import sources:"
        elif "export" in flow_phrase.lower():
            header = f"From {start_year} to {end_year}, Cambodia's {flow_phrase.strip()}{prod_phrase}{trans_phrase} grew across top export destinations:"

        bullets = []
        for r in latest_rows:
            ent = r.get(entity_key)
            rate = r.get("growth_rate_pct", 0.0)
            val_end = r.get("trade_value_usd", 0.0)

            ent_recs = sorted(entity_groups[ent], key=lambda x: str(x.get("period", "")))
            val_start = ent_recs[0].get("trade_value_usd", 0.0)

            val_start_str = format_metric(val_start, metrics)
            val_end_str = format_metric(val_end, metrics)

            # 3-period multi-entity step formatting (Rule 5)
            if len(all_periods) >= 3:
                steps = []
                for i in range(1, len(ent_recs)):
                    curr = ent_recs[i]
                    step_rate = curr.get("growth_rate_pct")
                    if step_rate is not None:
                        status_abbr = "+" if step_rate >= 0 else ""
                        steps.append(f"{status_abbr}{step_rate:.2f}% in {curr.get('period')}")
                steps_phrase = ", then ".join(steps)
                bullets.append(f"* {ent}: {steps_phrase} ({val_start_str} → {val_end_str})")
            else:
                bullets.append(f"* {ent}: {rate:+.2f}% ({val_start_str} → {val_end_str})")

        new_entrants_phrase = ""
        if new_entrants:
            new_entrants_phrase = f"\n\nNew entrants (no prior year data): {', '.join(new_entrants)}."

        return f"{header}\n" + "\n".join(bullets) + new_entrants_phrase
