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
