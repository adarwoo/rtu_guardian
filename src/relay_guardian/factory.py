class Device:
    def __init__(self, device_id: int, device_info: dict):
        self.device_id = device_id
        self.device_info = device_info

    def get_info(self):
        return self.device_info

    # When the device is
    def stop_polling(self):
        """Any background poll must stop"""

    def start_polling(self):
        """Any background poll must stop"""

    def ping(self):
        """Send a ping request to the device to check if the device still responds"""
        pass

class UnpluggedDevice(Device):
    def __init__(self, device_id: int, device_info: dict):
        super().__init__(device_id, device_info)

class UnknownDevice(Device):
    def __init__(self, device_id: int):
        super().__init__(device_id, {"info": "Unknown device"})


# Device factory
# This factory method gets information from the device and creates a device proxy.

# Scan device information
async def scan_device(device_id: int):
    # Start with function 17
    response = await modbus_request(device_id, function_code=17)
    if response:
        # Pass to factory
        factory_response = await device_factory.identify_device(response)
        if factory_response:
            return factory_response

    # If not supported or factory needs more, try function 43
    response = await modbus_request(device_id, function_code=43)
    if response:
        factory_response = await device_factory.identify_device(response)
        if factory_response:
            return factory_response

    # If all else fails, return basic info
    return {"device_id": device_id, "info": "Unknown device"}
