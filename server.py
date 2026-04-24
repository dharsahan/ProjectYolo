import argparse
import asyncio
import os

from bot import main as telegram_main
from discord_gateway import run_discord_gateway
from health_server import run_health_server


async def _serve(mode: str) -> None:
    tasks = []

    if mode in {"telegram", "all"}:
        # Run telegram polling in a worker thread.
        tasks.append(asyncio.create_task(asyncio.to_thread(telegram_main)))

    if mode in {"discord", "all"}:
        tasks.append(asyncio.create_task(run_discord_gateway()))

    if os.getenv("ENABLE_HEALTH_SERVER", "true").lower() == "true":
        host = os.getenv("HEALTH_SERVER_HOST", "0.0.0.0")
        port = int(os.getenv("HEALTH_SERVER_PORT", "8787"))
        tasks.append(
            asyncio.create_task(asyncio.to_thread(run_health_server, host, port))
        )

    if not tasks:
        raise RuntimeError("No gateway selected.")

    await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Yolo gateway server wrapper (Telegram/Discord-ready)."
    )
    parser.add_argument(
        "--mode",
        choices=["telegram", "discord", "all"],
        default="telegram",
        help="Gateway mode to start.",
    )
    args = parser.parse_args()
    asyncio.run(_serve(args.mode))


if __name__ == "__main__":
    main()
