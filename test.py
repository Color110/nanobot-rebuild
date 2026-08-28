import asyncio
import time


async def task(name: str) -> None:
    print(f"{name} start")
    await asyncio.sleep(2)
    print(f"{name} end")


async def main() -> None:
    start = time.perf_counter()

    await task("A"),
    await task("B"),
    await task("C"),
    time.sleep(2)
    
    elapsed = time.perf_counter() - start
    print(f"elapsed: {elapsed:.2f}s")


asyncio.run(main())