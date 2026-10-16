"""Read only live cluster sensor validation; credentials come from environment."""
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mqtt_display.core import MqttService, load_config
service=MqttService(load_config('examples/cluster-mqtt.yaml'))
service.start()
time.sleep(25)
for key in service.store.definitions:
    reading=service.store.snapshot(key)
    print(key,reading.status,reading.text)
service.stop()
