from mem0 import Memory
import os
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
    print("Testing add with user_id...")
    res = m.add([
        {"role": "user", "content": "hi my name is Dharshan"},
        {"role": "assistant", "content": "Hello Dharshan!"}
    ], user_id="test_user")
    print(f"Result: {res}")
except Exception as e:
    print(f"Error: {e}")
