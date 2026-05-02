from tools.yolo_memory import TieredMemoryEngine
import os

def test_all_tiers():
    db_file = "test_all_tiers.db"
    if os.path.exists(db_file):
        os.remove(db_file)
        
    try:
        engine = TieredMemoryEngine(db_path=db_file)
        user_id = 999
        
        print("--- Testing L1 Working Memory ---")
        engine.working_memory_set(user_id, "current_task", "Test all memory tiers")
        l1_mem = engine.working_memory_get(user_id)
        print(f"L1 Get: {l1_mem}")
        assert l1_mem.get("current_task") == "Test all memory tiers", "L1 set/get failed"
        
        print("\n--- Testing L2 Episodic Memory ---")
        engine.add("User started testing the system", user_id=str(user_id))
        stats = engine.memory_stats(user_id)
        print(f"Stats after 1 L2 insertion: {stats}")
        assert stats["L2_episodic_memory"] == 1, "L2 insertion failed"
        
        print("\n--- Testing L3 Semantic & L4 Pattern Memory (via Consolidation) ---")
        # To trigger L3, we need > 20 L2 memories
        print("Inserting 21 facts to trigger L3 consolidation...")
        for i in range(21):
            engine.add(f"Important fact {i} about the project", user_id=str(user_id))
            
        # To trigger L4, we need an event with importance >= 6.0 and keywords like "always", "never", "prefers"
        print("Inserting pattern memory trigger...")
        engine.add("The user always prefers dark mode", user_id=str(user_id))
        
        # Manually force consolidation to extract L4 pattern from L2
        engine.consolidate_memories(user_id)
        
        stats = engine.memory_stats(user_id)
        print(f"Stats after consolidation: {stats}")
        assert stats["L3_semantic_memory"] >= 1, "L3 consolidation failed"
        assert stats["L4_pattern_memory"] >= 1, "L4 pattern extraction failed"
        
        print("\n--- Testing Search & Get All ---")
        all_mems = engine.get_all(filters={"user_id": str(user_id)})
        print(f"Total memories retrieved: {len(all_mems)}")
        
        search_res = engine.search("dark mode", filters={"user_id": str(user_id)})
        print(f"Search 'dark mode': {search_res}")
        assert len(search_res) >= 1, "Search failed"
        
        print("\n--- Testing Deletion (All Tiers) ---")
        # Get IDs for each tier
        l1_id = next((m["id"] for m in all_mems if m["id"].startswith("l1_")), None)
        l2_id = next((m["id"] for m in all_mems if m["id"].startswith("l2_")), None)
        l3_id = next((m["id"] for m in all_mems if m["id"].startswith("l3_")), None)
        l4_id = next((m["id"] for m in all_mems if m["id"].startswith("l4_")), None)
        
        print(f"IDs to delete -> L1: {l1_id}, L2: {l2_id}, L3: {l3_id}, L4: {l4_id}")
        
        if l1_id: engine.delete(l1_id)
        if l2_id: engine.delete(l2_id)
        if l3_id: engine.delete(l3_id)
        if l4_id: engine.delete(l4_id)
        
        stats_after = engine.memory_stats(user_id)
        print(f"Stats after targeted deletion: {stats_after}")
        
        print("\n--- Testing Delete All ---")
        engine.delete_all(str(user_id))
        stats_final = engine.memory_stats(user_id)
        print(f"Stats after delete_all: {stats_final}")
        assert sum(stats_final.values()) == 0, "delete_all failed"
        
        print("\nSUCCESS: All L1, L2, L3, L4 memory functions operate correctly.")
        
    finally:
        if os.path.exists(db_file):
            os.remove(db_file)

if __name__ == "__main__":
    test_all_tiers()
