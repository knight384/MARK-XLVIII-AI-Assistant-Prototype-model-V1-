"""
core.memory.knowledge — Structured Knowledge Graph (Phase 11).

Provides Entity, Fact, and Relationship management over the SQLite store.
Adapted from donor vault implementation.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from .models import (
    EntityType, KnowledgeEntity, KnowledgeFact, KnowledgeRelationship,
    MemoryRecord, MemoryType, Source
)
from .stores.base import MemoryStore
from .stores.sqlite_store import SqliteMemoryStore

logger = logging.getLogger(__name__)

_STOPWORDS = {
    'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your',
    'yours', 'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her',
    'hers', 'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs',
    'themselves', 'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those',
    'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
    'having', 'do', 'does', 'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if',
    'or', 'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with',
    'about', 'against', 'between', 'through', 'during', 'before', 'after', 'above',
    'below', 'to', 'from', 'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under',
    'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why',
    'how', 'all', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such',
    'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
    'can', 'will', 'just', 'don', 'should', 'now', 'could', 'would', 'shall',
    'may', 'might', 'must', 'tell', 'know', 'think', 'say', 'said', 'get', 'go',
    'make', 'like', 'also', 'well', 'back', 'way', 'want', 'look', 'first', 'even',
    'give', 'yeah', 'yes', 'please', 'thanks', 'thank', 'hi', 'hello', 'hey',
    'okay', 'ok', 'sure', 'right', 'much', 'many', 'need', 'let', 'remember',
    'recall', 'told', 'mentioned', 'talked', 'work', 'works', 'working'
}

def extract_search_terms(message: str) -> list[str]:
    """Extract meaningful search terms from a message, skipping stopwords."""
    words = re.split(r"[^a-zA-Z0-9']+", message.lower())
    terms = []
    for w in words:
        w = w.strip("'")
        if len(w) > 1 and w not in _STOPWORDS:
            terms.append(w)
    return list(dict.fromkeys(terms))  # deduplicate preserving order


class KnowledgeMemory:
    """Manages structured knowledge entities, facts, and relationships."""
    
    def __init__(self, store: MemoryStore):
        # We require SqliteMemoryStore for structured storage, but accept MemoryStore in signature
        # to match existing DI patterns in MemoryService.
        self._store = store

    @property
    def _sql_store(self) -> SqliteMemoryStore | None:
        return self._store if isinstance(self._store, SqliteMemoryStore) else None

    def add_entity(self, name: str, entity_type: EntityType, properties: dict[str, Any] = None, source: Source = Source.SYSTEM, namespace: str = "global") -> KnowledgeEntity:
        if not self._sql_store:
            raise NotImplementedError("Structured knowledge requires SqliteMemoryStore")
        
        # Check if exists
        existing = self._sql_store.search_knowledge_entities(name=name, entity_type=entity_type, namespace=namespace)
        if existing:
            return existing[0]

        ent = KnowledgeEntity(name=name, entity_type=entity_type, properties=properties or {}, source=source, namespace=namespace)
        self._sql_store.save_knowledge_entity(ent)
        return ent

    def add_fact(self, subject_id: str, predicate: str, object_val: str, confidence: float = 1.0, source: Source = Source.SYSTEM, namespace: str = "global") -> KnowledgeFact:
        if not self._sql_store:
            raise NotImplementedError("Structured knowledge requires SqliteMemoryStore")
        
        fact = KnowledgeFact(subject_id=subject_id, predicate=predicate, object_val=object_val, confidence=confidence, source=source, namespace=namespace)
        self._sql_store.save_knowledge_fact(fact)
        return fact

    def add_relationship(self, from_id: str, to_id: str, rel_type: str, properties: dict[str, Any] = None, namespace: str = "global") -> KnowledgeRelationship:
        if not self._sql_store:
            raise NotImplementedError("Structured knowledge requires SqliteMemoryStore")
        
        rel = KnowledgeRelationship(from_id=from_id, to_id=to_id, rel_type=rel_type, properties=properties or {}, namespace=namespace)
        self._sql_store.save_knowledge_relationship(rel)
        return rel

    def retrieve_profiles_as_records(self, query: str, namespace: str | None = None) -> list[MemoryRecord]:
        """
        Adapted from donor `retrieval.ts`. Searches entities and facts matching the query,
        assembles full Entity Profiles (Entity + Facts + Relationships), and synthesizes
        them into MemoryRecords so they can be seamlessly ranked and injected by MemoryRetriever.
        """
        if not self._sql_store or not query:
            return []
            
        terms = extract_search_terms(query)
        if not terms:
            return []
            
        entity_map: dict[str, KnowledgeEntity] = {}
        
        # 1. Search entity names
        for term in terms:
            # We don't have LIKE for names currently in sqlite_store, but we can do a coarse fetch
            # Actually we can just implement search_knowledge_entities_by_term in store, or we fetch all and filter here.
            # Let's fetch all and filter since knowledge graph isn't millions of rows.
            # Or better, we only have exact match in store. Let's just fetch all entities for the namespace and filter.
            # (In production, adding LIKE index to SQLite is better, but this works for now)
            pass
            
        # Instead of manual fetching all, let's just use a custom query since we have lock access
        # Wait, we should not bypass store methods. I will add a search_knowledge_entities_by_term to store in a moment.
        # Let's assume we'll add it.
        
        matches = []
        for term in terms:
            matches.extend(self._sql_store.search_knowledge_entities_by_term(term, namespace))
            
        for ent in matches:
            entity_map[ent.entity_id] = ent
            
        # 2. Search facts
        for term in terms:
            facts = self._sql_store.search_knowledge_facts_by_term(term)
            for f in facts:
                if namespace and f.namespace != namespace:
                    continue
                if f.subject_id not in entity_map:
                    ent = self._sql_store.get_knowledge_entity(f.subject_id)
                    if ent:
                        entity_map[ent.entity_id] = ent

        # 3. Assemble Profiles
        records = []
        # Limit to top 10 entities to bound context
        for ent in list(entity_map.values())[:10]:
            facts = self._sql_store.get_knowledge_facts_for_subject(ent.entity_id)
            rels = self._sql_store.get_knowledge_relationships_for_entity(ent.entity_id)
            
            # Format as text
            lines = [f"Entity: {ent.name} ({ent.entity_type.value})"]
            for f in facts:
                lines.append(f"  - {f.predicate}: {f.object_val}")
            for r in rels:
                if r.from_id == ent.entity_id:
                    # Target is to_id
                    target = self._sql_store.get_knowledge_entity(r.to_id)
                    if target:
                        lines.append(f"  - {r.rel_type} -> {target.name}")
                else:
                    target = self._sql_store.get_knowledge_entity(r.from_id)
                    if target:
                        lines.append(f"  - {target.name} -> {r.rel_type} -> {ent.name}")
            
            content = "\n".join(lines)
            
            # Create a synthetic MemoryRecord for the retriever to rank
            record = MemoryRecord(
                content=content,
                memory_type=MemoryType.SEMANTIC,
                summary=f"Knowledge profile for {ent.name}",
                source=ent.source,
                importance=0.8, # Structured knowledge is generally highly relevant
                confidence=1.0,
                namespace=ent.namespace,
                metadata={"knowledge_profile": True, "entity_id": ent.entity_id, "entity_name": ent.name}
            )
            records.append(record)
            
        return records
