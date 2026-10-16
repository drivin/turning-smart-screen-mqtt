# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only MQTT collection, independent of GUI and upstream imports."""
from collections import deque
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import threading
import time

import yaml
from paho.mqtt import client as mqtt


@dataclass(frozen=True)
class Reading:
    number: float | None
    text: str
    history: tuple
    status: str


class SensorStore:
    def __init__(self, definitions, clock=time.monotonic):
        self.definitions = definitions
        self.clock = clock
        self.lock = threading.RLock()
        self.values = {}
        self.counters = {}
        self.history = {key: deque(maxlen=item.get('history', 60))
                        for key, item in definitions.items()}
        self.connected = False
        self.status = 'Disconnected'
        self.revision = 0

    def ingest(self, topic, payload):
        for key, definition in self.definitions.items():
            if definition['topic'] != topic:
                continue
            try:
                value = payload.decode('utf-8')
                if definition.get('path') is not None:
                    value = json.loads(value)
                    for part in definition['path']:
                        value = value[part]
                if definition['kind'] == 'number':
                    if isinstance(value, bool):
                        raise ValueError('Boolean is not a numeric sensor')
                    number = float(value)
                    if not math.isfinite(number):
                        raise ValueError('Non-finite numeric value')
                    if definition.get('rate', False):
                        with self.lock:
                            now = self.clock()
                            previous = self.counters.get(key)
                            self.counters[key] = (number, now)
                            if (previous is None or now <= previous[1] or number < previous[0]
                                    or now - previous[1] > definition['stale_after']):
                                self.values[key] = (None, 'Waiting for next sample', now, 'warming')
                                self.revision += 1
                                continue
                            number = (number - previous[0]) / (now - previous[1])
                    number *= definition.get('scale', 1)
                    if not math.isfinite(number):
                        raise ValueError('Non-finite numeric value')
                    text = f"{number:.{definition.get('decimals', 1)}f}{definition.get('unit', '')}"
                else:
                    if not isinstance(value, (str, int, float, bool)):
                        raise ValueError('Expected scalar text')
                    number, text = None, str(value)
            except (ValueError, TypeError, KeyError, IndexError, UnicodeError):
                with self.lock:
                    self.values[key] = (None, 'Invalid', self.clock(), 'invalid')
                    self.revision += 1
                continue
            with self.lock:
                if number is not None:
                    self.history[key].append(number)
                self.values[key] = (number, text, self.clock(), 'ok')
                self.revision += 1

    def snapshot(self, key):
        with self.lock:
            definition = self.definitions[key]
            number, text, received, status = self.values.get(
                key, (None, 'Waiting for data', self.clock(), 'missing'))
            if not self.connected:
                number, text, status = None, 'Disconnected', 'disconnected'
            elif status == 'ok' and self.clock() - received > definition['stale_after']:
                number, text, status = None, 'Stale', 'stale'
            history = tuple(self.history[key]) if status == 'ok' else ()
            # Upstream line rendering requires a fixed-length series, including at startup.
            history = (math.nan,) * (definition.get('history', 60) - len(history)) + history
            return Reading(number, text, history, status)


def load_config(path):
    path = Path(path).resolve()
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('sensors'), dict) or not data['sensors']:
        raise ValueError('Configuration requires sensors as a non-empty mapping.')
    broker = data['broker']
    if not isinstance(broker.get('host'), str) or not broker['host']:
        raise ValueError('broker.host is required.')
    if not isinstance(broker.get('port'), int) or not 1 <= broker['port'] <= 65535:
        raise ValueError('broker.port must be specified explicitly (1-65535).')
    if not isinstance(broker.get('tls'), bool):
        raise ValueError('broker.tls must be explicitly true or false.')
    for name, sensor in data['sensors'].items():
        if not isinstance(name, str) or not name.isidentifier() or not name.startswith('Mqtt'):
            raise ValueError('Sensor IDs must be Python identifiers starting with Mqtt.')
        if sensor.get('kind') not in ('number', 'text'):
            raise ValueError(f'{name}: kind must be number or text.')
        if 'rate' in sensor and (not isinstance(sensor['rate'], bool) or sensor['kind'] != 'number'):
            raise ValueError(f'{name}: rate must be a boolean and requires a numeric sensor.')
        topic = sensor.get('topic')
        if not isinstance(topic, str) or not topic or any(c in topic for c in ('+', '#', '\x00')):
            raise ValueError(f'{name}: an exact MQTT topic is required.')
        if not isinstance(sensor.get('stale_after'), (int, float)) or sensor['stale_after'] <= 0:
            raise ValueError(f'{name}: stale_after must be explicitly positive.')
        if 'path' in sensor and (not isinstance(sensor['path'], list) or
                               any(not isinstance(p, (str, int)) for p in sensor['path'])):
            raise ValueError(f'{name}: path must be a list of JSON keys/indices.')
        if not isinstance(sensor.get('history', 60), int) or not 2 <= sensor.get('history', 60) <= 10000:
            raise ValueError(f'{name}: history must be between 2 and 10000.')
        if not isinstance(sensor.get('decimals', 1), int) or not 0 <= sensor.get('decimals', 1) <= 12:
            raise ValueError(f'{name}: decimals must be between 0 and 12.')
        scale = sensor.get('scale', 1)
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale):
            raise ValueError(f'{name}: scale must be a finite number.')
    return data


class MqttService:
    def __init__(self, config):
        self.config = config
        self.store = SensorStore(config['sensors'])
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        broker = config['broker']
        user_env, password_env = broker.get('username_env'), broker.get('password_env')
        if user_env:
            username = os.environ.get(user_env)
            password = os.environ.get(password_env) if password_env else None
            if username is None or (password_env and password is None):
                raise ValueError('MQTT credentials are missing from the configured environment variables.')
            self.client.username_pw_set(username, password)
        if broker['tls']:
            self.client.tls_set(ca_certs=broker.get('ca_file'))
        self.client.on_connect = self._connect
        self.client.on_disconnect = self._disconnect
        self.client.on_connect_fail = self._failed
        self.client.on_subscribe = self._subscribed
        self.client.on_message = lambda c, u, m: self.store.ingest(m.topic, m.payload)
        self.client.connect_timeout = 5
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

    def _connect(self, client, userdata, flags, reason, properties):
        with self.store.lock:
            self.store.counters.clear()
            self.store.connected = not reason.is_failure
            self.store.status = 'Connected' if not reason.is_failure else f'Login rejected: {reason}'
        if not reason.is_failure:
            client.subscribe([(topic, 0) for topic in sorted(
                {s['topic'] for s in self.config['sensors'].values()})])

    def _subscribed(self, client, userdata, mid, reasons, properties):
        if any(reason.is_failure for reason in reasons):
            with self.store.lock:
                self.store.status = 'At least one topic subscription was rejected'

    def _disconnect(self, client, userdata, flags, reason, properties):
        with self.store.lock:
            self.store.connected = False
            self.store.status = 'Disconnected; reconnecting'

    def _failed(self, client, userdata):
        with self.store.lock:
            self.store.connected = False
            self.store.status = 'Broker unreachable; retrying'

    def start(self):
        broker = self.config['broker']
        self.client.connect_async(broker['host'], broker['port'], keepalive=30)
        self.client.loop_start()

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()


def register_sensors(module, store):
    """Bind adapters without modifying upstream sources or existing class names."""
    conflicts = [key for key in store.definitions if hasattr(module, key)]
    if conflicts:
        raise ValueError('Sensor names already registered: ' + ', '.join(conflicts))

    def make_class(key):
        class Adapter(module.CustomDataSource):
            def __init__(self):
                self.reading = store.snapshot(key)

            def as_numeric(self):
                return self.reading.number

            def as_string(self):
                return self.reading.text

            def last_values(self):
                return list(self.reading.history)
        Adapter.__name__ = key
        return Adapter

    for key in store.definitions:
        setattr(module, key, make_class(key))
