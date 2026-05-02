from tools.memory_service import get_memory
from tools.yolo_memory import TieredMemoryEngine
import os

os.environ["YOLO_MEMORY_ENGINE"] = ""
memory = get_memory()
print("Memory type:", type(memory))
print("Is TieredMemoryEngine:", isinstance(memory, TieredMemoryEngine))
