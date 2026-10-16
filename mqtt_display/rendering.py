# SPDX-License-Identifier: GPL-3.0-or-later
"""Batch native TURZX updates into one USB transfer per rendering group."""
from contextlib import contextmanager
from functools import wraps
import logging
import threading
import time


class FrameBatch:
    def __init__(self, lcd):
        self.lcd = lcd
        self.original = lcd.DisplayPILImage
        self.lock = threading.RLock()
        self.depth = 0
        self.dirty = False
        self.updates = 0
        self.frames_sent = 0
        lcd.DisplayPILImage = self.draw

    def draw(self, image, x=0, y=0, image_width=0, image_height=0):
        with self.lock:
            if not self.depth:
                return self.original(image, x, y, image_width, image_height)
            width = min(image_width or image.width, self.lcd.get_width())
            height = min(image_height or image.height, self.lcd.get_height())
            if (width, height) != image.size:
                image = image.crop((0, 0, width, height))
            self.lcd.current_state.paste(image, (x, y))
            self.dirty = True
            self.updates += 1

    @contextmanager
    def frame(self):
        with self.lock:
            outer = self.depth == 0
            if outer:
                previous = self.lcd.current_state.copy()
                self.dirty = False
                self.updates = 0
            self.depth += 1
            try:
                yield
            except BaseException:
                if outer:
                    self.lcd.current_state = previous
                    self.dirty = False
                raise
            finally:
                self.depth -= 1
            if outer and self.dirty:
                image = self.lcd.current_state.copy()
                self.dirty = False
                started = time.monotonic()
                self.original(image, 0, 0, image.width, image.height)
                self.frames_sent += 1
                if self.frames_sent <= 3:
                    logging.getLogger(__name__).info('TURZX frame: %d drawing updates, one USB transfer, %.2fs',
                                                     self.updates, time.monotonic()-started)

    def wrap(self, function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with self.frame():
                return function(*args, **kwargs)
        return wrapped


def install_display(module):
    display = module.display
    # Opt-in caller also checks config; simulated and other display drivers are untouched.
    if type(display.lcd).__name__ != 'LcdCommTuringUSB':
        return
    if hasattr(display, '_mqtt_frame_batch'):
        return
    batch = FrameBatch(display.lcd)
    display._mqtt_frame_batch = batch
    logging.getLogger(__name__).info('TURZX frame batching enabled')
    for name in ('display_static_images', 'display_static_text'):
        setattr(display, name, batch.wrap(getattr(display, name)))


def install_stats(module):
    from .pages import controller
    original = module.Custom.stats
    started = False
    @wraps(original)
    def render():
        nonlocal started
        if not started:
            controller.started = controller.clock()
            started = True
        if controller.apply(module.config):
            module.display.display_static_images()
            module.display.display_static_text()
        return original()
    batch = getattr(module.display, '_mqtt_frame_batch', None)
    module.Custom.stats = staticmethod(batch.wrap(render) if batch is not None else render)
