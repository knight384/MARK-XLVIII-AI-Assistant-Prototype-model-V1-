import sys
import logging
from pathlib import Path

from core.memory.service import get_default_memory_service
from core.memory.models import EntityType, RetrievalQuery

logging.basicConfig(level=logging.INFO)

def main():
    print("--- LIVE VERIFICATION (PHASE 11) ---")
    svc = get_default_memory_service()
    
    k = svc.knowledge
    
    print("\n1. Creating knowledge...")
    p1 = k.add_entity("Tony Stark", EntityType.PERSON)
    p2 = k.add_entity("Avengers Tower", EntityType.PLACE)
    
    print("2. Attaching facts & relationships...")
    k.add_fact(p1.entity_id, "is_a", "superhero")
    k.add_fact(p1.entity_id, "builds", "suits")
    k.add_relationship(p1.entity_id, p2.entity_id, "owns", {"legal_entity": "Stark Industries"})
    
    print("3. Retrieving context via MemoryService...")
    query = RetrievalQuery(query="Where does Tony Stark live and what does he build?")
    results = svc.retrieve(query)
    
    found_knowledge = False
    for r in results:
        if r.record.metadata.get("knowledge_profile"):
            found_knowledge = True
            print(f"\n=> Retrieved Knowledge Profile (Relevance: {r.relevance:.2f}):")
            print("-" * 40)
            print(r.record.content)
            print("-" * 40)
            
    if found_knowledge:
        print("\nSUCCESS: Knowledge profiles are automatically synthesized and injected into MemoryRetriever.")
    else:
        print("\nFAILURE: Knowledge profile was not retrieved.")

if __name__ == "__main__":
    main()
