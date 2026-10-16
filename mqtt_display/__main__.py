# SPDX-License-Identifier: GPL-3.0-or-later
"""Check configured live sensors without starting the display application."""
import argparse
import time

from .core import MqttService, load_config


def main():
    parser = argparse.ArgumentParser(description='Read configured MQTT sensors without publishing')
    parser.add_argument('--config', required=True)
    parser.add_argument('--seconds', type=float, default=10)
    args = parser.parse_args()
    service = MqttService(load_config(args.config))
    service.start()
    try:
        time.sleep(args.seconds)
        print(service.store.status)
        for key in service.store.definitions:
            value = service.store.snapshot(key)
            print(f'{key}: {value.text} [{value.status}]')
    finally:
        service.stop()


if __name__ == '__main__':
    main()
