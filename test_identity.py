import os
from prompt_builder import _build_memory_context, _derive_identity_hints, _extract_memory_lines
from tools.yolo_memory import TieredMemoryEngine

if os.path.exists("test_identity.sqlite"):
    os.remove("test_identity.sqlite")

engine = TieredMemoryEngine(db_path="test_identity.sqlite")
engine.add("user: i am dharshan\nassistant: Hello, Dharshan. How can I assist you today?", "1")
engine.add("user: my name id dharshan\nassistant: Hello Dharshan. How can I assist you today?", "1")
engine.add("user: who am i\nassistant: You are the user interacting with YOLO.", "1")

print("All memories in engine:")
for m in engine.get_all(filters={"user_id": "1"}):
    print(m)

print("\nTesting _build_memory_context:")
res = _build_memory_context(engine, 1, "who am i")
print(res)

print("\nTesting _derive_identity_hints directly:")
lines = _extract_memory_lines(engine.get_all(filters={"user_id": "1"}))
hints = _derive_identity_hints(lines)
print(hints)
