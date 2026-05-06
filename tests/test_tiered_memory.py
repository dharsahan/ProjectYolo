from tools.yolo_memory import TieredMemoryEngine

def test_db_initialization(tmp_path):
    db_path = tmp_path / "test_memory.db"
    engine = TieredMemoryEngine(db_path=db_path)
    assert db_path.exists()
    
    # Check tables exist
    tables = engine.get_tables()
    assert "L1_working_memory" in tables
    assert "L2_episodic_memory" in tables
    assert "L3_semantic_memory" in tables
    assert "L4_pattern_memory" in tables

def test_working_memory(tmp_path):
    db_path = tmp_path / "test_memory.db"
    engine = TieredMemoryEngine(db_path=db_path)
    engine.working_memory_set(1, "current_goal", "Fix bug")
    
    mem = engine.working_memory_get(1)
    assert mem["current_goal"] == "Fix bug"
    
    engine.working_memory_clear(1)
    assert len(engine.working_memory_get(1)) == 0

def test_importance_scoring():
    engine = TieredMemoryEngine(db_path=":memory:")
    score_id = engine._score_importance("My name is Dharshan", "identity")
    assert score_id > 8.0
    
    score_low = engine._score_importance("ok", "fact")
    assert score_low < 3.0

def test_mem0_interface(tmp_path):
    db_path = tmp_path / "test_memory.db"
    engine = TieredMemoryEngine(db_path=db_path)
    engine.add("My name is Dharshan and I love coding", "1")
    engine.add("ok", "1")  # Should be filtered as noise

    all_mems = engine.get_all(filters={"user_id": "1"})
    assert len(all_mems) == 1
    assert "Dharshan" in all_mems[0]["memory"]

    # Test consolidate
    for i in range(25):
        engine.add(f"Important fact {i}", "1")

    all_mems_after = engine.get_all(filters={"user_id": "1"})
    assert len(all_mems_after) >= 26
    
    # Test search
    results = engine.search("Dharshan", filters={"user_id": "1"})
    assert len(results) >= 1
    
    # Test delete
    engine.delete(all_mems_after[0]["id"])
    assert len(engine.get_all(filters={"user_id": "1"})) >= 25

    # Test delete_all
    engine.delete_all("1")
    assert len(engine.get_all(filters={"user_id": "1"})) == 0

def test_get_recent_summary(tmp_path):
    from tools.yolo_memory import TieredMemoryEngine
    db_path = tmp_path / "test_memory.db"
    engine = TieredMemoryEngine(db_path=db_path)
    
    # Add a semantic fact
    engine.add("My favorite color is blue.", "1", category="preference")
    engine.consolidate_memories(1)

    # Add an episodic memory (will stay in L2 until next consolidation)
    engine.add("I had a great day today.", "1")
    
    summary = engine.get_recent_summary(user_id=1, limit=5)
    
    # Should only contain the semantic memory (L3/L4), not the L2 blob
    assert len(summary) == 1
    assert "blue" in summary[0]["memory"]

