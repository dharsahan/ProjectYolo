from mem0 import Memory
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

config = {
    "llm": {
        "provider": "openai",
        "config": {"api_key": os.getenv("OPENAI_API_KEY"), "model": "gpt-4o"},
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "path": "test_memory/qdrant",
        },
    },
}

try:
    m = Memory.from_config(config)
    print("Testing get_all with user_id...")
    res = m.get_all(user_id="test_user")
    print(f"Result: {res}")
except Exception as e:
    print(f"Error: {e}")

try:
    print("\nTesting get_all with filters={'user_id': ...}")
    res = m.get_all(filters={"user_id": "test_user"})
    print(f"Result: {res}")
except Exception as e:
    print(f"Error: {e}")

try:
    print("\nTesting get_all with filters={'userid': ...}")
    res = m.get_all(filters={"userid": "test_user"})
    print(f"Result: {res}")
except Exception as e:
    print(f"Error: {e}")
