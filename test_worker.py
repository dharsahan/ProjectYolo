import asyncio
from tools.team_ops import spawn_worker
from tools.database_ops import get_worker_status

async def main():
    spawn_worker(1, "test_role", "Do something simple")
    await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
