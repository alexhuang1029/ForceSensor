
from nexgraphpy import NexGraph

DFT_DEVICE = NexGraph()

if DFT_DEVICE.find():
    if DFT_DEVICE.connect():
        print(DFT_DEVICE.get_info())
        DFT_DEVICE.disconnect()
        DFT_DEVICE = None
    else:
        print("Unable to connect")
        exit()
else:
    print("No device found.")
    exit()