"""Build DAL requests from parsed service parameters."""

from __future__ import annotations

from typing import Any, Mapping

from .dal_models import DALRequest


class DALRequestBuilder:
    """Convert parsed query params into the universal DAL request format."""

    def build_request(self, intent: str, params: Mapping[str, Any]) -> DALRequest:
        """Build a DALRequest from normalized parsed parameters.

        This intentionally only reshapes data. It does not apply business rules
        or choose query logic.
        """

        data = dict(params)

        period, start_period, end_period, frequency = self._build_time_window(data)
        filters = self._build_filters(data)
        metrics = self._build_metrics(data)
        
        raw_group_by = self._build_group_by(data)
        explicit_dimensions = data.get("dimensions")
        if isinstance(explicit_dimensions, list):
            raw_dimensions = [str(item) for item in explicit_dimensions if str(item).strip()]
        else:
            raw_dimensions = list(dict.fromkeys(raw_group_by or ["PARTNER_COUNTRY", "FLOW"]))

        # Filter out PERIOD, FREQ, FREQUENCY, and any time-based names which are
        # returned automatically by the DAL but are NOT valid concept dimensions.
        # Valid DAL dimensions: FLOW, HS_CHAPTER, HS_HEADING, MODE_OF_TRANSPORT,
        #   PARTNER_COUNTRY, SITC_DIVISION, SITC_SECTION
        invalid_concept_dims = {"PERIOD", "FREQ", "FREQUENCY"}
        dimensions = [d for d in raw_dimensions if d.upper() not in invalid_concept_dims]
        group_by = [g for g in raw_group_by if g.upper() not in invalid_concept_dims]

        # Ensure at least one valid dimension is always present (DAL requires it)
        if not dimensions:
            dimensions = ["FLOW"] if intent in ("trend", "summary", "trade_balance") else ["PARTNER_COUNTRY"]
        if not group_by:
            group_by = ["FLOW"] if intent in ("trend", "summary", "trade_balance") else ["PARTNER_COUNTRY"]

        known_keys = {
            "origin_country",
            "destination_country",
            "mode_of_transport",
            "year",
            "month",
            "quarter",
            "hs_code",
            "trade_direction",
            "trade_volume",
            "trade_value",
            "limit",
            "offset",
            "period",
            "start_period",
            "end_period",
            "frequency",
            "sort",
            "sort_order",
            "sort_metric",
            "metrics",
            "group_by",
            "dimensions",
            "filters",
        }
        extra = {key: value for key, value in data.items() if key not in known_keys}

        # Resolve sort: explicit 'sort' param wins; otherwise derive from sort_order
        sort = data.get("sort")
        if not sort:
            sort_metric = data.get("sort_metric", "VALUE_USD")
            sort_order = data.get("sort_order")
            if sort_order == "asc":
                sort = f"{sort_metric}:asc"
            elif sort_order == "desc" or intent == "ranking":
                sort = f"{sort_metric}:desc"

        return DALRequest(
            intent=intent,
            filters=filters,
            metrics=metrics,
            group_by=group_by,
            dimensions=dimensions,
            version=data.get("version"),
            start_period=start_period,
            end_period=end_period,
            period=period,
            frequency=frequency,
            sort=sort,
            limit=int(data.get("limit", 1000) or 1000),
            offset=int(data.get("offset", 0) or 0),
            extra=extra,
        )

    def _build_filters(self, params: Mapping[str, Any]) -> dict[str, Any]:
        filters: dict[str, Any] = {}

        partner_countries = params.get("partner_countries")
        if isinstance(partner_countries, list) and partner_countries:
            if len(partner_countries) == 1:
                filters["PARTNER_COUNTRY"] = partner_countries[0]
            else:
                filters["PARTNER_COUNTRY"] = partner_countries
        else:
            partner_country = None
            origin_country = params.get("origin_country")
            destination_country = params.get("destination_country")
            
            if origin_country == "KH":
                if destination_country and destination_country != "KH":
                    partner_country = destination_country
            elif destination_country == "KH":
                if origin_country and origin_country != "KH":
                    partner_country = origin_country
            else:
                if destination_country and destination_country != "KH":
                    partner_country = destination_country
                elif origin_country and origin_country != "KH":
                    partner_country = origin_country
                    
            if partner_country is not None and str(partner_country).strip():
                filters["PARTNER_COUNTRY"] = partner_country

        trade_direction = params.get("trade_direction")
        if trade_direction is not None and str(trade_direction).strip():
            filters["FLOW"] = trade_direction

        hs_chapter = params.get("hs_chapter")
        if hs_chapter is not None:
            if isinstance(hs_chapter, list):
                # Multi-chapter comparison — pass list directly
                chapters = [str(c).strip() for c in hs_chapter if str(c).strip()]
                if chapters:
                    filters["HS_CHAPTER"] = chapters if len(chapters) > 1 else chapters[0]
            elif str(hs_chapter).strip():
                filters["HS_CHAPTER"] = str(hs_chapter).strip()


        hs_code = params.get("hs_code")
        if hs_code is not None and str(hs_code).strip():
            if len(str(hs_code)) == 4:
                filters["HS_HEADING"] = hs_code
            else:
                filters["HS_CODE"] = hs_code

        transport_mode = params.get("mode_of_transport")
        if transport_mode is not None and str(transport_mode).strip():
            filters["MODE_OF_TRANSPORT"] = transport_mode

        if isinstance(params.get("filters"), dict):
            filters.update(params["filters"])

        return filters

    def _build_metrics(self, params: Mapping[str, Any]) -> list[str]:
        metrics = params.get("metrics")
        if isinstance(metrics, list):
            return [str(item) for item in metrics if str(item).strip()]

        return ["VALUE_USD", "NET_WEIGHT"]

    def _build_group_by(self, params: Mapping[str, Any]) -> list[str]:
        group_by = params.get("group_by")
        if isinstance(group_by, list):
            return [self._map_group_dimension(str(item)) for item in group_by if str(item).strip()]

        inferred = ["PARTNER_COUNTRY"]
        if params.get("trade_direction") is not None:
            inferred.append("FLOW")
        return inferred

    def _map_group_dimension(self, value: str) -> str:
        # NOTE: "period" / "PERIOD" is intentionally mapped to empty string so it
        # is stripped by the invalid_concept_dims filter. The DAL does NOT accept
        # PERIOD as a concept dimension; time window is controlled via the
        # period/start-period/end-period/frequency query params.
        mapping = {
            "origin_country": "PARTNER_COUNTRY",
            "destination_country": "PARTNER_COUNTRY",
            "mode_of_transport": "MODE_OF_TRANSPORT",
            "hs_code": "HS_CHAPTER",
            "HS_CODE": "HS_CHAPTER",
            "hs_chapter": "HS_CHAPTER",
            "HS_CHAPTER": "HS_CHAPTER",
            "hs_heading": "HS_HEADING",
            "HS_HEADING": "HS_HEADING",
            "trade_direction": "FLOW",
            "partner_country": "PARTNER_COUNTRY",
            "flow": "FLOW",
            # Time-based values — map to PERIOD so they are caught by the filter
            "period": "PERIOD",
            "month": "PERIOD",
            "year": "PERIOD",
            "quarter": "PERIOD",
        }
        return mapping.get(value, value.upper() if value.upper() in {
            "HS_CHAPTER", "HS_HEADING", "HS_CODE", "PARTNER_COUNTRY",
            "FLOW", "MODE_OF_TRANSPORT",
        } else value)

    def _build_time_window(self, params: Mapping[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
        """Translate year/quarter/month inputs into DAL time parameters."""

        period = params.get("period")
        if isinstance(period, str) and period.strip():
            frequency = params.get("frequency")
            return period, params.get("start_period"), params.get("end_period"), frequency

        start_period = params.get("start_period")
        end_period = params.get("end_period")
        if start_period or end_period:
            return None, start_period, end_period, params.get("frequency")

        year = params.get("year")
        quarter = params.get("quarter")
        month = params.get("month")

        if year is None:
            return None, None, None, params.get("frequency")

        year_text = str(year)
        if quarter:
            return f"{year_text}-{quarter}", None, None, params.get("frequency") or "Q"

        if month is not None:
            month_text = str(month).zfill(2)
            return f"{year_text}-{month_text}", None, None, params.get("frequency") or "M"

        return year_text, None, None, params.get("frequency") or "A"
