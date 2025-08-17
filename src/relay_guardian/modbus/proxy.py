import asyncio


class DeviceProxy:
    def __init__(self, device_id: int):
        self.device_id = device_id

    async def report_slave_id(self):
        # Simulate scanning the device
        await asyncio.sleep(1)
        return None

    async def query_mei(self):
        # Simulate querying the device
        await asyncio.sleep(1)
        return None