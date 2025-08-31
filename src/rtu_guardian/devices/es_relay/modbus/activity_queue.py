import asyncio
from collections import deque

class CommandQueue:
    def __init__(self):
        self.queue = deque()
        self.executing = asyncio.Lock()

    def enqueue(self, cmd: str, priority: bool = False):
        if cmd in self.queue:
            return  # skip duplicates

        if priority:
            self.queue.appendleft(cmd)  # user query
        else:
            self.queue.append(cmd)      # poll command

    async def execute_loop(self):
        while True:
            if self.queue:
                async with self.executing:
                    cmd = self.queue.popleft()
                    await self.execute(cmd)
            await asyncio.sleep(0.1)  # prevent tight loop

    async def execute(self, cmd: str):
        print(f"Executing: {cmd}")
        await asyncio.sleep(1)  # simulate device communication

# Usage
queue = CommandQueue()

async def poller():
    while True:
        queue.enqueue("poll_temperature")
        await asyncio.sleep(5)

async def user_interaction():
    queue.enqueue("read_sensor_A", priority=True)

async def main():
    asyncio.create_task(queue.execute_loop())
    asyncio.create_task(poller())
    await user_interaction()

asyncio.run(main())
