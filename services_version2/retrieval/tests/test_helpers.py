"""
Unit tests for the pure / lexical classification logic in ``app/api/endpoints.py``.

These tests do **not** touch Qdrant, Redis, or Gemini — they exercise the
regex / scoring helpers directly, which is where most of the actual
classification behaviour (constraint parsing, cc-range matching, hard
filtering, confidence scoring, text humanisation) lives.

Run with::

    pytest tests/test_helpers.py -v
"""

import pytest

from app.api import endpoints as ep


# =========================================================================
# _normalize_hs_digits / _hs_code_family
# =========================================================================


class TestNormalizeHsDigits:
    """Unit tests for HS-code digit normalisation."""

    def test_strips_dots_and_dashes(self):
        """Dots and dashes are removed; only first 6 digits kept."""
        assert ep._normalize_hs_digits("8703.23.10") == "870323"

    def test_short_code_returns_none(self):
        """Fewer than 6 digits → None."""
        assert ep._normalize_hs_digits("8703") is None

    def test_none_input(self):
        """None input → None."""
        assert ep._normalize_hs_digits(None) is None

    def test_empty_string(self):
        """Empty string → None."""
        assert ep._normalize_hs_digits("") is None

    def test_exact_six_digits(self):
        """Exactly 6 digits → same 6 digits."""
        assert ep._normalize_hs_digits("870323") == "870323"

    def test_longer_than_six_truncates(self):
        """More than 6 digits → truncated to first 6."""
        assert ep._normalize_hs_digits("87032310") == "870323"


class TestHsCodeFamily:
    """_hs_code_family is the same logic applied to any value type."""

    def test_basic(self):
        """Standard dotted HS code → 6-digit prefix."""
        assert ep._hs_code_family("8703.23.10") == "870323"

    def test_none(self):
        """None → None."""
        assert ep._hs_code_family(None) is None

    def test_non_string_int(self):
        """Integer HS codes are stringified correctly."""
        assert ep._hs_code_family(870323) == "870323"


# =========================================================================
# CC-range extraction / matching
# =========================================================================


class TestCcRanges:
    """
    Tests for ``_extract_cc_ranges`` and ``_matches_cc``.

    These parse HS description text like "exceeding 1500 cc but not
    exceeding 3000 cc" into numeric intervals and test whether a given
    cc value falls inside.
    """

    def test_between_range_matches(self):
        """Compound range: 2000 cc is inside (1500, 3000]."""
        text = "exceeding 1500 cc but not exceeding 3000 cc"
        assert ep._matches_cc(2000, text) is True
        assert ep._matches_cc(1500, text) is False  # exclusive lower bound
        assert ep._matches_cc(3000, text) is True   # inclusive upper bound

    def test_between_range_KNOWN_QUIRK_upper_bound_not_enforced(self):
        """
        KNOWN QUIRK: the standalone "exceeding X cc" regex also matches
        the "exceeding 3000 cc" tail of a "but not exceeding 3000 cc"
        phrase, spuriously adding an unbounded (3000, None) range. As a
        result values ABOVE the stated upper bound still match.

        This is documented and tested so the behaviour does not change
        silently.
        """
        text = "exceeding 1500 cc but not exceeding 3000 cc"
        assert ep._extract_cc_ranges(text) == [(1500, 3000), (3000, None)]
        assert ep._matches_cc(3500, text) is True  # should arguably be False

    def test_exceeding_only(self):
        """"exceeding X cc" — unbounded upper, exclusive lower."""
        text = "exceeding 3000 cc"
        assert ep._matches_cc(3500, text) is True
        assert ep._matches_cc(3000, text) is False

    def test_not_exceeding_only(self):
        """"not exceeding Y cc" — unbounded lower, inclusive upper."""
        text = "not exceeding 1000 cc"
        assert ep._matches_cc(999, text) is True
        assert ep._matches_cc(1000, text) is True

    def test_not_exceeding_only_KNOWN_QUIRK_no_upper_enforcement(self):
        """
        KNOWN QUIRK: the standalone "exceeding X cc" regex also catches
        "not exceeding 1000 cc", adding a spurious unbounded (1000, None)
        range, so values above the stated upper bound still match.

        Documented and tested to prevent silent behaviour changes.
        """
        text = "not exceeding 1000 cc"
        assert ep._extract_cc_ranges(text) == [(1000, None), (None, 1000)]
        assert ep._matches_cc(1001, text) is True  # should arguably be False

    def test_no_cc_info_defaults_to_match(self):
        """No cc constraint in text → can't rule out → True."""
        assert ep._matches_cc(2500, "a generic passenger vehicle") is True

    def test_comma_separated_numbers(self):
        """Comma-separated thousands are parsed correctly."""
        text = "exceeding 1,500 cc but not exceeding 3,000 cc"
        assert ep._matches_cc(2000, text) is True


# =========================================================================
# _derive_vehicle_constraints
# =========================================================================


class TestDeriveVehicleConstraints:
    """
    Tests for the vehicle-constraint parser that extracts structured
    attributes (assembly, fuel, body, drive, cc) from free-text queries.
    """

    def test_all_fields_default_none(self):
        """Non-vehicle query → all constraints are None."""
        c = ep._derive_vehicle_constraints("a plain product with no vehicle terms")
        assert c == {
            "assembly": None, "fuel": None, "body": None,
            "drive": None, "cc": None,
        }

    def test_cbu_detected_as_non_ckd(self):
        """CBU / assembled → assembly=non_ckd."""
        assert ep._derive_vehicle_constraints("Toyota Hilux CBU")["assembly"] == "non_ckd"

    def test_ckd_detected(self):
        """CKD / knocked down → assembly=ckd."""
        assert ep._derive_vehicle_constraints("Toyota Hilux CKD kit")["assembly"] == "ckd"

    def test_diesel_fuel(self):
        """diesel → fuel=diesel."""
        assert ep._derive_vehicle_constraints("2000cc diesel engine truck")["fuel"] == "diesel"

    def test_spark_ignition_synonym_petrol(self):
        """petrol → fuel=spark."""
        assert ep._derive_vehicle_constraints("petrol sedan")["fuel"] == "spark"

    def test_electric_fuel(self):
        """electric / EV → fuel=electric."""
        assert ep._derive_vehicle_constraints("electric vehicle")["fuel"] == "electric"

    def test_hybrid_fuel(self):
        """hybrid / PHEV → fuel=hybrid."""
        assert ep._derive_vehicle_constraints("plug-in hybrid SUV")["fuel"] == "hybrid"

    def test_body_sedan(self):
        """sedan → body=sedan."""
        assert ep._derive_vehicle_constraints("Honda Civic sedan")["body"] == "sedan"

    def test_body_pickup_variants(self):
        """Both "pick-up" and "pickup" are recognised."""
        assert ep._derive_vehicle_constraints("pick-up truck")["body"] == "pickup"
        assert ep._derive_vehicle_constraints("pickup truck")["body"] == "pickup"

    def test_drive_4wd_variants(self):
        """4WD / 4x4 / AWD / all-wheel → drive=4wd."""
        for phrase in ["4WD", "4x4", "AWD", "all-wheel drive"]:
            assert (
                ep._derive_vehicle_constraints(f"car {phrase}")["drive"] == "4wd"
            ), phrase

    def test_drive_KNOWN_GAP_spelled_out_four_wheel_not_matched(self):
        """
        KNOWN GAP: "four-wheel drive" (spelled out) is NOT matched because
        the regex requires the digit "4". This is documented and tested.
        """
        c = ep._derive_vehicle_constraints("car four-wheel drive")
        assert c["drive"] is None  # arguably should be "4wd"

    def test_drive_2wd(self):
        """2WD → drive=2wd."""
        assert ep._derive_vehicle_constraints("car 2WD")["drive"] == "2wd"

    def test_cc_extraction(self):
        """Numeric value followed by 'cc' is extracted."""
        assert ep._derive_vehicle_constraints("BMW M8, 4395cc, petrol")["cc"] == 4395

    def test_model_name_infers_suv_and_4wd_defaults(self):
        """
        Bare model names with 2+ digits (e.g. RX350) are defaulted to
        body=suv, drive=4wd.
        """
        c = ep._derive_vehicle_constraints("Lexus RX350")
        assert c["body"] == "suv"
        assert c["drive"] == "4wd"

    def test_model_name_single_digit_KNOWN_GAP_not_detected(self):
        """
        KNOWN GAP: "X5" has only one digit, so the model-name heuristic
        (which requires ≥2 digits) does not trigger.
        """
        c = ep._derive_vehicle_constraints("BMW X5")
        assert c["body"] is None
        assert c["drive"] is None

    def test_model_name_does_not_override_explicit_sedan(self):
        """Explicit "sedan" overrides the model-name SUV default."""
        c = ep._derive_vehicle_constraints("BMW M8 sedan")
        assert c["body"] == "sedan"

    def test_excluded_vehicle_types_not_defaulted_to_suv(self):
        """Ambulance, hearse, etc. are excluded from the SUV default."""
        c = ep._derive_vehicle_constraints("ambulance A4")
        assert c["body"] is None


# =========================================================================
# _candidate_support_score
# =========================================================================


class TestCandidateSupportScore:
    """Unit tests for the candidate confidence scoring function."""

    def make_doc(self, content):
        """Helper: create a minimal doc dict with just content."""
        return {"content": content, "metadata": {}}

    def test_empty_text_or_query_scores_zero(self):
        """Empty query or document → score 0.0."""
        assert ep._candidate_support_score("", self.make_doc("something")) == 0.0
        assert ep._candidate_support_score("something", self.make_doc("")) == 0.0

    def test_matching_fuel_boosts_score(self):
        """A diesel query scores higher against a diesel doc than a petrol doc."""
        query = "diesel truck"
        good = self.make_doc("Motor vehicle, compression-ignition (diesel) engine")
        bad = self.make_doc("Motor vehicle, spark-ignition petrol engine")
        assert ep._candidate_support_score(query, good) > ep._candidate_support_score(query, bad)

    def test_score_bounded_between_0_and_1(self):
        """Scores are always clamped to [0.0, 1.0]."""
        query = "diesel 4wd suv 3000cc CBU"
        doc = self.make_doc(
            "suv diesel compression-ignition 4wd cbu exceeding 2500 cc "
            "but not exceeding 3500 cc"
        )
        score = ep._candidate_support_score(query, doc)
        assert 0.0 <= score <= 1.0

    def test_suv_query_penalizes_ambulance_doc(self):
        query = "SUV vehicle"  # explicit "suv" keyword sets body=suv constraint
        ambulance_doc = self.make_doc("ambulance, specially fitted vehicle")
        suv_doc = self.make_doc("suv, sport utility vehicle, 4wd")
        assert ep._candidate_support_score(query, suv_doc) > ep._candidate_support_score(query, ambulance_doc)
        assert ep._candidate_support_score(query, ambulance_doc) == 0.0


class TestHsResultConfident:
    def test_empty_docs_not_confident(self):
        assert ep._hs_result_confident("anything", []) is False

    def test_strong_match_is_confident(self):
        docs = [{"content": "diesel compression-ignition suv 4wd exceeding 2500 cc but not exceeding 3500 cc", "metadata": {}}]
        assert ep._hs_result_confident("diesel suv 4wd 3000cc", docs) is True

    def test_weak_match_not_confident(self):
        docs = [{"content": "unrelated textile fabric product", "metadata": {}}]
        assert ep._hs_result_confident("diesel suv 4wd 3000cc", docs) is False


# ---------------------------------------------------------------------------
# _humanize_hs_text
# ---------------------------------------------------------------------------

class TestHumanizeHsText:
    def test_empty_text(self):
        assert ep._humanize_hs_text("") == "Short description unavailable"
        assert ep._humanize_hs_text(None) == "Short description unavailable"

    def test_strips_breadcrumb_separators(self):
        text = "Vehicles > Motor cars > Sedans"
        result = ep._humanize_hs_text(text)
        assert ">" not in result

    def test_deduplicates_segments(self):
        text = "Sedans; Sedans; Sedans"
        result = ep._humanize_hs_text(text)
        assert result.count("Sedans") == 1

    def test_drops_generic_leading_heading(self):
        text = ("Motor cars and other motor vehicles principally designed for the transport of persons; "
                "spark-ignition; sedan")
        result = ep._humanize_hs_text(text)
        assert "principally designed" not in result.lower()

    def test_truncates_to_140_chars(self):
        text = "a" * 500
        result = ep._humanize_hs_text(text)
        assert len(result) <= 140


# ---------------------------------------------------------------------------
# _filter_docs_to_hs_prefix_family
# ---------------------------------------------------------------------------

class TestFilterDocsToPrefixFamily:
    def test_no_prefix_returns_all(self):
        docs = [{"metadata": {"hs_code": "870323"}}]
        assert ep._filter_docs_to_hs_prefix_family(docs, None) == docs

    def test_filters_to_matching_family(self):
        docs = [
            {"metadata": {"hs_code": "8703.23.10"}},
            {"metadata": {"hs_code": "8703.32.10"}},
        ]
        result = ep._filter_docs_to_hs_prefix_family(docs, "870323")
        assert len(result) == 1
        assert result[0]["metadata"]["hs_code"] == "8703.23.10"

    def test_empty_match_falls_back_to_all_docs(self):
        docs = [{"metadata": {"hs_code": "8703.32.10"}}]
        # prefix doesn't match anything -> fallback returns original docs, not empty
        result = ep._filter_docs_to_hs_prefix_family(docs, "999999")
        assert result == docs


# ---------------------------------------------------------------------------
# _apply_hard_vehicle_filters
# ---------------------------------------------------------------------------

class TestApplyHardVehicleFilters:
    def test_diesel_filter_excludes_petrol_docs(self):
        docs = [
            {"content": "diesel compression-ignition vehicle"},
            {"content": "spark-ignition petrol vehicle"},
        ]
        filtered, meta = ep._apply_hard_vehicle_filters("diesel vehicle", docs)
        assert len(filtered) == 1
        assert "diesel" in filtered[0]["content"]
        assert meta["filter_input_count"] == 2
        assert meta["filter_output_count"] == 1

    def test_no_constraints_keeps_all_docs(self):
        docs = [{"content": "some product"}, {"content": "another product"}]
        filtered, meta = ep._apply_hard_vehicle_filters("generic query no constraints", docs)
        assert filtered == docs

    def test_cc_filter(self):
        docs = [
            {"content": "vehicle exceeding 1000 cc but not exceeding 1500 cc"},
            {"content": "vehicle exceeding 3000 cc but not exceeding 3500 cc"},
        ]
        filtered, _ = ep._apply_hard_vehicle_filters("1200cc vehicle", docs)
        assert len(filtered) == 1
        assert "1000 cc" in filtered[0]["content"]


# ---------------------------------------------------------------------------
# transform_document
# ---------------------------------------------------------------------------

class TestTransformDocument:
    def test_basic_transform(self):
        doc = {"id": "1", "content": "some description", "score": 0.8, "hs_code": "870323"}
        result = ep.transform_document(doc)
        assert result["id"] == "1"
        assert result["content"] == "some description"
        assert result["score"] == 0.8
        assert result["metadata"]["hs_code"] == "870323"

    def test_missing_id_defaults_to_unknown(self):
        doc = {"content": "x"}
        result = ep.transform_document(doc)
        assert result["id"] == "unknown"

    def test_content_truncated_to_1000_chars(self):
        doc = {"id": "1", "content": "a" * 2000}
        result = ep.transform_document(doc)
        assert len(result["content"]) == 1000

    def test_missing_score_defaults_to_half(self):
        doc = {"id": "1", "content": "x", "score": None}
        result = ep.transform_document(doc)
        assert result["score"] == 0.5


# ---------------------------------------------------------------------------
# build_ranked_hs_answer (async, no gemini_client -> extractive fallback path)
# ---------------------------------------------------------------------------

class TestBuildRankedHsAnswer:
    @pytest.mark.asyncio
    async def test_generate_answer_false_returns_empty(self):
        result = await ep.build_ranked_hs_answer("query", [{"content": "x"}], generate_answer=False)
        assert result["final_answer"] is None

    @pytest.mark.asyncio
    async def test_no_docs_returns_no_results_message(self):
        result = await ep.build_ranked_hs_answer("query", [], generate_answer=True)
        assert result["answer_source"] == "no_results"
        assert "No HS code candidates" in result["final_answer"]

    @pytest.mark.asyncio
    async def test_extractive_fallback_without_gemini_client(self):
        docs = [
            {"content": "diesel compression-ignition vehicle", "metadata": {"hs_code": "8703.32.10"}, "score": 0.9},
            {"content": "spark-ignition petrol vehicle", "metadata": {"hs_code": "8703.23.10"}, "score": 0.7},
        ]
        result = await ep.build_ranked_hs_answer("diesel vehicle", docs, generate_answer=True, gemini_client=None)
        assert result["answer_source"] == "extractive_ranked"
        assert "8703.32.10" in result["final_answer"]