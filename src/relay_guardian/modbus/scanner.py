# Scanner for Modbus RTU devices

# Scan a single device

# Start with the legacy function 17 (Report Slave ID)
# If supported → ✅ gives you a string with slave ID info (often manufacturer / model / version).
# Pass this information to the factory which may ask for more.
# If not, supported → or factory needs more - try more modern function 43.
# If supported → ✅ you get vendor, product code, firmware, serial number, etc. (structured metadata).
# Pass this information to the factory.
# If the factory identifies the device, it should return a device proxy and UI elements for interaction.
# Else, create a simple information sheet with whatever information collected.

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