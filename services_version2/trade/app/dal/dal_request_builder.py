"""Build DAL requests from finalized Query Plans.

Acts as a pure serializer. Does not perform NLP reasoning, synonym resolution,
or intent/flow decisions.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Union

from app.dal.dal_models import DALRequest
from app.schemas.query_plan import FinalQueryPlan


class DALRequestBuilder:
    """Convert pre-validated finalized query plans into the universal DAL request format."""

    def build_from_plan(self, plan: FinalQueryPlan) -> DALRequest:
        """Map a finalized FinalQueryPlan directly to a DALRequest without logic (Stage 5 Serialization)."""
        metrics = list(plan.metrics)
        if "QUANTITY" in metrics and "QUANTITY.UNIT" not in metrics:
            metrics.append("QUANTITY.UNIT")
        return DALRequest(
            intent=plan.intent,
            filters=plan.filters,
            metrics=metrics,
            group_by=plan.group_by,
            dimensions=plan.dimensions,
            version=plan.version,
            start_period=plan.start_period,
            end_period=plan.end_period,
            period=plan.period,
            frequency=plan.frequency,
            sort=plan.sort,
            limit=plan.limit,
            offset=plan.offset,
            extra=plan.extra,
        )

    def build_request(self, intent: Union[str, FinalQueryPlan], params: Optional[Mapping[str, Any]] = None) -> DALRequest:
        """Construct a DALRequest from a FinalQueryPlan or legacy mapping dictionary."""
        if isinstance(intent, FinalQueryPlan):
            return self.build_from_plan(intent)

        # Legacy dict fallback: reconstruct FinalQueryPlan and serialize it
        data = dict(params or {})

        period, start_period, end_period, frequency = self._build_time_window(data)

        filters = data.get("filters") or {}
        if not filters:
            filters = self._build_filters(data)

        metrics = self._build_metrics(data)
        dimensions, group_by = self._build_group_by_and_dimensions(str(intent), data)
        sort = self._build_sort(str(intent), data)

        known_keys = {
            "origin_country", "destination_country", "partner_country", "partner_countries",
            "mode_of_transport", "year", "month", "quarter", "semester", "hs_code", "hs_chapter",
            "trade_direction", "trade_volume", "trade_value", "limit", "offset", "period",
            "start_period", "end_period", "frequency", "sort", "sort_order", "sort_metric",
            "metrics", "group_by", "dimensions", "filters", "version", "sitc_section", "sitc_division"
        }
        extra = {key: value for key, value in data.items() if key not in known_keys}

        plan = FinalQueryPlan(
            intent=str(intent),
            version=data.get("version", "trade_volume_1.0"),
            filters=filters,
            metrics=metrics,
            group_by=group_by,
            dimensions=dimensions,
            period=period,
            start_period=start_period,
            end_period=end_period,
            frequency=frequency,
            sort=sort,
            limit=int(data.get("limit", 1000) or 1000),
            offset=int(data.get("offset", 0) or 0),
            extra=extra,
        )

        return self.build_from_plan(plan)

    def _build_filters(self, params: Mapping[str, Any]) -> dict[str, Any]:
        filters: dict[str, Any] = {}

        # Partner Country Mapping
        partner_countries = params.get("partner_countries")
        if isinstance(partner_countries, list) and partner_countries:
            valid_countries = [c for c in partner_countries if str(c).strip()]
            if len(valid_countries) == 1:
                filters["PARTNER_COUNTRY"] = valid_countries[0]
            elif valid_countries:
                filters["PARTNER_COUNTRY"] = valid_countries
        else:
            partner_country = params.get("partner_country")
            if not partner_country:
                origin = params.get("origin_country")
                dest = params.get("destination_country")
                if origin == "KH" and dest and dest != "KH":
                    partner_country = dest
                elif dest == "KH" and origin and origin != "KH":
                    partner_country = origin
                else:
                    partner_country = dest or origin
            if partner_country and str(partner_country).strip():
                filters["PARTNER_COUNTRY"] = str(partner_country).strip()

        # Flow Direction Mapping
        trade_direction = params.get("trade_direction")
        if trade_direction and str(trade_direction).strip():
            filters["FLOW"] = str(trade_direction).strip()

        # HS Chapter Mapping
        hs_chapter = params.get("hs_chapter")
        if hs_chapter:
            if isinstance(hs_chapter, list):
                valid_chapters = [str(c).strip() for c in hs_chapter if str(c).strip()]
                if len(valid_chapters) == 1:
                    filters["HS_CHAPTER"] = valid_chapters[0]
                elif valid_chapters:
                    filters["HS_CHAPTER"] = valid_chapters
            elif str(hs_chapter).strip():
                filters["HS_CHAPTER"] = str(hs_chapter).strip()

        # HS Code Mapping
        hs_code = params.get("hs_code")
        if hs_code and str(hs_code).strip():
            code_str = str(hs_code).strip()
            if len(code_str) == 4:
                filters["HS_HEADING"] = code_str
            else:
                filters["HS_CODE"] = code_str

        # SITC Section Mapping
        sitc_section = params.get("sitc_section")
        if sitc_section and str(sitc_section).strip():
            filters["SITC_SECTION"] = str(sitc_section).strip()

        # SITC Division Mapping
        sitc_division = params.get("sitc_division")
        if sitc_division and str(sitc_division).strip():
            filters["SITC_DIVISION"] = str(sitc_division).strip()

        # Mode of Transport Mapping
        transport_mode = params.get("mode_of_transport")
        if transport_mode:
            if isinstance(transport_mode, list):
                valid_modes = [str(m).strip() for m in transport_mode if str(m).strip()]
                if len(valid_modes) == 1:
                    filters["MODE_OF_TRANSPORT"] = valid_modes[0]
                elif valid_modes:
                    filters["MODE_OF_TRANSPORT"] = valid_modes
            elif str(transport_mode).strip():
                filters["MODE_OF_TRANSPORT"] = str(transport_mode).strip()

        return filters

    def _build_metrics(self, params: Mapping[str, Any]) -> list[str]:
        metrics = params.get("metrics")
        if isinstance(metrics, list) and metrics:
            result = [str(m).strip() for m in metrics if str(m).strip()]
            if "QUANTITY" in result and "QUANTITY.UNIT" not in result:
                result.append("QUANTITY.UNIT")
            return result
        return ["VALUE_USD", "NET_WEIGHT"]

    def _build_group_by_and_dimensions(self, intent: str, params: Mapping[str, Any]) -> tuple[list[str], list[str]]:
        group_by = params.get("group_by")
        dimensions = params.get("dimensions")

        raw_dims = [str(d) for d in dimensions] if isinstance(dimensions, list) else []
        raw_group = [str(g) for g in group_by] if isinstance(group_by, list) else []

        if not raw_dims and not raw_group:
            inferred = ["FLOW", "PARTNER_COUNTRY"] if intent in ("trend", "summary", "trade_balance", "growth") else ["PARTNER_COUNTRY"]
            raw_dims = inferred
            raw_group = inferred
        elif not raw_dims:
            raw_dims = raw_group
        elif not raw_group:
            raw_group = raw_dims

        time_keys = {"PERIOD", "FREQ", "FREQUENCY"}
        dimensions_list = [d for d in raw_dims if d.upper() not in time_keys]
        group_by_list = [g for g in raw_group if g.upper() not in time_keys]

        if not dimensions_list:
            dimensions_list = ["FLOW"] if intent in ("trend", "summary", "trade_balance", "growth") else ["PARTNER_COUNTRY"]
        if not group_by_list:
            group_by_list = ["FLOW"] if intent in ("trend", "summary", "trade_balance", "growth") else ["PARTNER_COUNTRY"]

        return dimensions_list, group_by_list

    def _build_sort(self, intent: str, params: Mapping[str, Any]) -> str | None:
        sort = params.get("sort")
        if sort:
            return sort

        sort_metric = params.get("sort_metric", "VALUE_USD")
        sort_order = params.get("sort_order")
        if sort_order == "asc":
            return f"{sort_metric}:asc"
        elif sort_order == "desc" or intent == "ranking":
            return f"{sort_metric}:desc"
        return None

    def _build_time_window(self, params: Mapping[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
        period = params.get("period")
        if isinstance(period, str) and period.strip():
            return period, params.get("start_period"), params.get("end_period"), params.get("frequency")

        start_period = params.get("start_period")
        end_period = params.get("end_period")
        if start_period or end_period:
            return None, start_period, end_period, params.get("frequency")

        year = params.get("year")
        quarter = params.get("quarter")
        month = params.get("month")
        semester = params.get("semester")

        if year is None:
            return None, None, None, params.get("frequency")

        year_text = str(year)
        if quarter:
            return f"{year_text}-{quarter}", None, None, params.get("frequency") or "Q"

        if semester is not None:
            return f"{year_text}-S{semester}", None, None, params.get("frequency") or "S"

        if month is not None:
            month_text = str(month).zfill(2)
            return f"{year_text}-{month_text}", None, None, params.get("frequency") or "M"

        return year_text, None, None, params.get("frequency") or "A"
