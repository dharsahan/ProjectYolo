import pytest
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
