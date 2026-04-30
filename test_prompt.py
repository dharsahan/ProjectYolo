import sys
from tools.yolo_memory import TieredMemoryEngine
from prompt_builder import _build_memory_context

engine = TieredMemoryEngine(db_path=":memory:")
engine.add("My name is Dharshan and I love coding", "1")
engine.add("I always write unit tests", "1")

res = _build_memory_context(engine, 1, "who am i")
print("RESULT:\n", res)
