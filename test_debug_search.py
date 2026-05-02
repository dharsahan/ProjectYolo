from tools.yolo_memory import TieredMemoryEngine
import os
if os.path.exists("test_debug.sqlite"):
    os.remove("test_debug.sqlite")
engine = TieredMemoryEngine(db_path="test_debug.sqlite")
engine.add("My name is Dharshan and I love coding", "1")
for i in range(25):
    engine.add(f"Important fact {i}", "1")
print("ALL MEMS:")
print(engine.get_all(filters={"user_id": "1"}))
print("SEARCH RESULTS:")
print(engine.search("Dharshan", filters={"user_id": "1"}))
