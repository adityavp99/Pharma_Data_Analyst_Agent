from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.semantic_tool import (
    get_metric_definition,
    get_relevant_semantic_context,
    load_business_glossary,
    load_join_paths,
    load_metric_definitions,
    load_ontology,
)


def test_metric_definitions_load() -> None:
    metrics = load_metric_definitions()
    assert "enrollment_rate" in metrics
    assert "SUM(enrolled_patients)" in metrics["enrollment_rate"]["formula"]


def test_get_metric_definition_normalizes_spaces() -> None:
    metric = get_metric_definition("enrollment rate")
    assert metric is not None
    assert metric["tables"] == ["sites"]


def test_ontology_and_glossary_load() -> None:
    ontology = load_ontology()
    glossary = load_business_glossary()
    assert ontology["Trial"]["source_table"] == "trials"
    assert "Net sales" in glossary


def test_relevant_semantic_context_keyword_search() -> None:
    context = get_relevant_semantic_context("What is the enrollment rate?")
    assert "enrollment_rate" in context
    assert "Enrollment rate" in context


def test_join_paths_load() -> None:
    joins = load_join_paths()
    assert "relationships" in joins
    assert joins["relationships"]["trials_to_sites"]["join_condition"] == "trials.trial_id = sites.trial_id"
