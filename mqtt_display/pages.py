# SPDX-License-Identifier: GPL-3.0-or-later
"""Foreground pages, rendered by the existing scheduler / GUI thread."""
from functools import wraps
import logging
import time


class Pages:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = None
        self.index = None

    def apply(self, config):
        theme = config.THEME_DATA
        pages = theme.get('MQTT_PAGES')
        if not pages:
            return False
        now = self.clock()
        if self.started is None:
            self.started = now
        # Scheduler queues its next invocation immediately before drawing. Allow
        # its sub-millisecond dispatch jitter at the exact 20-second boundary.
        index = int((now-self.started+0.05)/pages['INTERVAL']) % len(pages['VIEWS'])
        changed = index != self.index
        self.index = index
        page = pages['VIEWS'][index]
        theme['static_text'] = page['static_text']
        theme['STATS']['CUSTOM'] = page['CUSTOM']
        theme['_MQTT_PAGE_INDEX'] = index
        if changed:
            logging.getLogger('turing').info('MQTT view %d/%d', index+1, len(pages['VIEWS']))
        return changed


controller = Pages()


def install_config(module):
    original = module.load_theme

    @wraps(original)
    def load():
        original()
        controller.apply(module)

    module.load_theme = load
    controller.apply(module)
