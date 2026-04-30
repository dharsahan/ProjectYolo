import os
from session import Session
from prompt_builder import _build_memory_context, _merge_memory_context_into_system_prompt
from tools.yolo_memory import TieredMemoryEngine

if os.path.exists("test_merge.sqlite"):
    os.remove("test_merge.sqlite")

engine = TieredMemoryEngine(db_path="test_merge.sqlite")
engine.add("user: i am dharshan\nassistant: Hello, Dharshan. How can I assist you today?", "1")

session = Session(user_id=1)

res = _build_memory_context(engine, 1, "who am i")
print("MEMORY CONTEXT RETURNED:")
print(res)

_merge_memory_context_into_system_prompt(session, res)
print("\nSYSTEM PROMPT AFTER MERGE:")
print(session.message_history[0]["content"])
