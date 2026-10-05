import time
import os
import sqlite3
from pathlib import Path

import pytest

from core.memory.models import EntityType, Source, RetrievalQuery
from core.memory.service import MemoryService
from core.memory.stores.sqlite_store import SqliteMemoryStore
from core.memory.stores.json_store import JsonMemoryStore
from core.memory.policies import MemoryConfig
from core.memory.knowledge import KnowledgeMemory, extract_search_terms

@pytest.fixture
def memory_service(tmp_path):
    pref_store = JsonMemoryStore(tmp_path / "pref.json")
    durable_store = SqliteMemoryStore(tmp_path / "mem.db")
    config = MemoryConfig(memory_enabled=True)
    svc = MemoryService(pref_store, durable_store, config)
    return svc

def test_extract_search_terms():
    terms = extract_search_terms("Hello! Does John Doe work at Acme Corp?")
    assert "john" in terms
    assert "doe" in terms
    assert "acme" in terms
    assert "corp" in terms
    assert "does" not in terms  # stopwords

def test_entity_persistence(memory_service):
    k = memory_service.knowledge
    
    ent = k.add_entity("John Doe", EntityType.PERSON, {"role": "CEO"}, Source.USER, "project_alpha")
    assert ent.name == "John Doe"
    assert ent.entity_type == EntityType.PERSON
    
    # search it
    results = k._sql_store.search_knowledge_entities(name="John Doe")
    assert len(results) == 1
    assert results[0].properties["role"] == "CEO"

def test_fact_persistence(memory_service):
    k = memory_service.knowledge
    ent = k.add_entity("John Doe", EntityType.PERSON)
    fact = k.add_fact(ent.entity_id, "works_at", "Acme Corp")
    
    facts = k._sql_store.get_knowledge_facts_for_subject(ent.entity_id)
    assert len(facts) == 1
    assert facts[0].predicate == "works_at"
    assert facts[0].object_val == "Acme Corp"

def test_relationship_persistence(memory_service):
    k = memory_service.knowledge
    p1 = k.add_entity("John Doe", EntityType.PERSON)
    p2 = k.add_entity("Jane Smith", EntityType.PERSON)
    
    rel = k.add_relationship(p1.entity_id, p2.entity_id, "manages", {"department": "Engineering"})
    
    rels = k._sql_store.get_knowledge_relationships_for_entity(p1.entity_id)
    assert len(rels) == 1
    assert rels[0].rel_type == "manages"
    assert rels[0].properties["department"] == "Engineering"

def test_retrieval_ranking_and_context_assembly(memory_service):
    k = memory_service.knowledge
    
    ent = k.add_entity("Project Phoenix", EntityType.PROJECT)
    k.add_fact(ent.entity_id, "status", "active")
    
    p1 = k.add_entity("John Doe", EntityType.PERSON)
    k.add_relationship(p1.entity_id, ent.entity_id, "leads")
    
    # query retrieval
    q = RetrievalQuery(query="Who leads Project Phoenix?")
    results = memory_service.retrieve(q)
    
    # should contain the knowledge profile
    found = False
    for r in results:
        if r.record.metadata.get("knowledge_profile"):
            found = True
            assert "Project Phoenix" in r.record.content
            assert "leads" in r.record.content
    
    assert found, "Knowledge profile was not retrieved!"

def test_namespace_behavior(memory_service):
    k = memory_service.knowledge
    ent_a = k.add_entity("Secret Project", EntityType.PROJECT, namespace="ns_A")
    ent_b = k.add_entity("Public Project", EntityType.PROJECT, namespace="ns_B")
    
    # Searching specifically in ns_B shouldn't yield ns_A entities via retrieval (though retrieval currently uses coarse query)
    q = RetrievalQuery(query="Project", namespace="ns_B")
    results = memory_service.retrieve(q)
    
    for r in results:
        if r.record.metadata.get("knowledge_profile"):
            assert r.record.namespace == "ns_B"
            assert "Public Project" in r.record.content
            assert "Secret Project" not in r.record.content
