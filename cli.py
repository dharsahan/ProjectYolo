import argparse
import asyncio

import agent
from session import SessionManager


async def repl(user_id: int) -> None:
    session_manager = SessionManager(timeout_minutes=60)
    session = session_manager.get_or_create(user_id)

    print("Yolo CLI ready. Type `exit` to quit.")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break

        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            break

        try:
            response = await agent.run_agent_turn(
                text,
                session,
                signal_handler=None,
                memory_service=session_manager.memory,
            )
            print(f"yolo> {response}")
            session_manager.save(user_id)
        except agent.PendingConfirmationError as e:
            print(f"yolo> Confirmation needed: {e.action} -> {e.path}")
            decision = input("Approve? (y/N): ").strip().lower()
            if decision in {"y", "yes"}:
                result = await agent.execute_tool_direct(
                    e.action,
                    e.tool_args,
                    user_id,
                    signal_handler=None,
                    session=session,
                )
                print(f"tool> {result}")
                response = await agent.run_agent_turn(
                    None,
                    session,
                    signal_handler=None,
                    memory_service=session_manager.memory,
                )
                print(f"yolo> {response}")
            else:
                print("yolo> Action denied.")

            session_manager.save(user_id)
        except Exception as e:
            print(f"yolo> Error: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Yolo personal CLI")
    parser.add_argument("--user-id", type=int, default=1, help="Local CLI user id")
    args = parser.parse_args()
    asyncio.run(repl(args.user_id))


if __name__ == "__main__":
    main()
