import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from app.utils.text_utils import strip_clarification_questions_from_prose


def test_no_questions_returns_original_text():
    prose = "Some random response with no questions."
    assert strip_clarification_questions_from_prose(prose, []) == prose
    assert strip_clarification_questions_from_prose(prose, None) == prose


def test_empty_text_returns_empty():
    assert strip_clarification_questions_from_prose("", ["Some question?"]) == ""


def test_header_based_truncation_case_insensitive():
    prose = (
        "Here is the main answer.\n"
        "\n"
        "[Clarification Questions]\n"
        "- What is the engine size?\n"
        "- Is it CKD or CBU?"
    )
    expected = "Here is the main answer."
    questions = ["What is the engine size?", "Is it CKD or CBU?"]
    assert strip_clarification_questions_from_prose(prose, questions) == expected


def test_header_variants_truncation():
    variants = [
        "clarification questions:",
        "Clarification Questions",
        "[CLARIFICATION QUESTIONS]",
        "clarifying questions:",
    ]
    questions = ["Test?"]
    for var in variants:
        prose = f"Main answer.\n\n{var}\n- Test?"
        assert strip_clarification_questions_from_prose(prose, questions) == "Main answer."


def test_orphaned_header_prevention():
    # If the header exists, everything below it should be cut,
    # preventing an orphaned header like "[Clarification Questions]" at the end.
    prose = (
        "Main answer.\n"
        "[Clarification Questions]\n"
        "- This question was paraphrased differently?"
    )
    questions = ["Different question?"]
    assert strip_clarification_questions_from_prose(prose, questions) == "Main answer."


def test_bullet_scoped_exact_matching():
    prose = (
        "Main answer.\n"
        "- What is the engine size?\n"
        "* Is it CKD or CBU?\n"
        "❓ Does it have 4WD?"
    )
    questions = ["What is the engine size?", "Is it CKD or CBU?", "Does it have 4WD?"]
    expected = "Main answer."
    assert strip_clarification_questions_from_prose(prose, questions) == expected


def test_fuzzy_normalized_matching():
    # Test normalization (ignoring casing, bullet chars, trailing question marks, extra spaces)
    prose = (
        "Main answer.\n"
        "  -  what is the   engine size  \n"
        " 1. is it ckd or cbu\n"
        "❓ does it have 4wd"
    )
    questions = ["What is the engine size?", "Is it CKD or CBU?", "Does it have 4WD?"]
    expected = "Main answer."
    assert strip_clarification_questions_from_prose(prose, questions) == expected


def test_bullet_scoped_substring_matching():
    # Test substring matching (Tier 3 fallback)
    prose = (
        "Main answer.\n"
        "- The engine capacity size must be specified?\n"
        "- Is it imported as CKD/CBU parts?"
    )
    questions = ["What is the engine capacity size?", "Is it CKD/CBU?"]
    expected = "Main answer."
    assert strip_clarification_questions_from_prose(prose, questions) == expected


def test_over_strip_prevention():
    # Crucial: Unrelated prose sentences containing the question keywords must NOT be stripped
    # because they do not start with list/bullet markers.
    prose = (
        "The engine capacity size is highly relevant for duty classification.\n"
        "Please select from the options below:\n"
        "- What is the engine capacity size?"
    )
    # The first line has "engine capacity size" but is normal prose. It should be kept.
    # The last line starts with a bullet and matches, so it should be stripped.
    questions = ["What is the engine capacity size?"]
    expected = (
        "The engine capacity size is highly relevant for duty classification.\n"
        "Please select from the options below:"
    )
    assert strip_clarification_questions_from_prose(prose, questions) == expected


def test_non_question_lists_preserved():
    prose = (
        "Main answer.\n"
        "\n"
        "[Sources]\n"
        "- Customs Book 2026\n"
        "- Subheading 8703"
    )
    questions = ["Test?"]
    # Sources list doesn't match the questions and should be preserved
    assert strip_clarification_questions_from_prose(prose, questions) == prose


def test_khmer_and_bilingual_punctuation():
    prose = (
        "ចម្លើយចម្បង。\n"
        "- តើទំហំម៉ាស៊ីនប៉ុន្មាន? \n"
        "- តើវាជា CKD ឬ CBU ដែរឬទេ?។"
    )
    questions = ["តើទំហំម៉ាស៊ីនប៉ុន្មាន?", "តើវាជា CKD ឬ CBU ដែរឬទេ?"]
    expected = "ចម្លើយចម្បង。"
    assert strip_clarification_questions_from_prose(prose, questions) == expected
