"""tests/memory/test_semantic.py"""
from __future__ import annotations

from core.memory.models import Source
from core.memory.semantic import SemanticMemory


def test_remember_fact(durable_store):
    sm = SemanticMemory(durable_store)
    record = sm.remember_fact("Python is dynamically typed", concept="python", confidence=0.9)
    assert record.content == "Python is dynamically typed"
    assert record.confidence == 0.9


def test_facts_about_concept(durable_store):
    sm = SemanticMemory(durable_store)
    sm.remember_fact("fact 1", concept="python")
    sm.remember_fact("fact 2", concept="python")
    sm.remember_fact("unrelated", concept="cooking")
    facts = sm.facts_about("python")
    assert len(facts) == 2


def test_facts_about_ordered_by_confidence(durable_store):
    sm = SemanticMemory(durable_store)
    sm.remember_fact("low confidence fact", concept="x", confidence=0.3)
    sm.remember_fact("high confidence fact", concept="x", confidence=0.95)
    facts = sm.facts_about("x")
    assert facts[0].content == "high confidence fact"


def test_all_facts_filtered_by_namespace(durable_store):
    sm = SemanticMemory(durable_store)
    sm.remember_fact("a", namespace="ns1")
    sm.remember_fact("b", namespace="ns2")
    assert len(sm.all_facts(namespace="ns1")) == 1


def test_provenance_defaults(durable_store):
    sm = SemanticMemory(durable_store)
    record = sm.remember_fact("inferred fact", source=Source.AGENT)
    assert record.source == Source.AGENT
