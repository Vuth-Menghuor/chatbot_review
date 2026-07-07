"""Unit tests for period parsing and pattern matching."""

import pytest

from app.schemas.metadata import PeriodFilterConcept
from app.utils.period_parser import split_period


class TestMatchPeriodPattern:
    def test_match_yyyy(self):
        start, end = split_period("2025")
        assert start == "2025"
        assert end == "2025"

    def test_match_yyyy_mm(self):
        start, end = split_period("2025-01")
        assert start == "2025-01"
        assert end == "2025-01"

    def test_match_yyyy_q1(self):
        start, end = split_period("2025-Q1")
        assert start == "2025-Q1"
        assert end == "2025-Q1"

    def test_match_yyyy_q1_lowercase(self):
        start, end = split_period("2025-q1")
        assert start == "2025-q1"
        assert end == "2025-q1"

    def test_no_match(self):
        with pytest.raises(ValueError):
            split_period("invalid")

    def test_match_range_yyyy(self):
        start, end = split_period("2020-2025")
        assert start == "2020"
        assert end == "2025"
        
    def test_match_range_yyyy_mm(self):
        start, end = split_period("2020-01 - 2025-12")
        assert start == "2020-01"
        assert end == "2025-12"
        
    def test_match_range_yyyy_q(self):
        start, end = split_period("2020-Q1 - 2025-Q4")
        assert start == "2020-Q1"
        assert end == "2025-Q4"
        
    def test_match_range_yyyy_s(self):
        start, end = split_period("2020-S1 - 2025-S2")
        assert start == "2020-S1"
        assert end == "2025-S2"
        
    def test_match_range_yyyy_q_lowercase(self):
        start, end = split_period("2020-q1 - 2025-q4")
        assert start == "2020-q1"
        assert end == "2025-q4"
        
    def test_match_range_yyyy_s_lowercase(self):
        start, end = split_period("2020-s1 - 2025-s2")
        assert start == "2020-s1"
        assert end == "2025-s2"
        
    def test_invalid_range(self):
        with pytest.raises(ValueError):
            split_period("2020-01 - invalid")
    
    def test_invalid_format(self):
        with pytest.raises(ValueError):
            split_period("2020/01/01 - 2025/12/31")
    
    def test_different_formats(self):
        with pytest.raises(ValueError):
            split_period("2020-01 - 2025-Q4")
