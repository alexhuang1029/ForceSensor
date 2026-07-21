import asyncio
from open_gopro import WirelessGoPro

async def test_ble():
    print("Searching for HERO12 BLE signal...")
    async with WirelessGoPro() as gopro:
        print("Connected successfully over BLE!")
        print(f"Camera model: {gopro.identifier}")

asyncio.run(test_ble())