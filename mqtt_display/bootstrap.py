# SPDX-License-Identifier: GPL-3.0-or-later
"""Opt-in import hooks scoped to the configured upstream checkout."""
import atexit
import importlib.abc
import importlib.machinery
import os
from pathlib import Path
import sys

_service = None
_installed = False


def get_service():
    global _service
    if _service is None:
        from .core import MqttService, load_config
        _service = MqttService(load_config(os.environ['TURZX_MQTT_CONFIG']))
        atexit.register(_service.stop)
    return _service


class HookLoader(importlib.abc.Loader):
    def __init__(self, original, callback):
        self.original, self.callback = original, callback

    def create_module(self, spec):
        return self.original.create_module(spec)

    def exec_module(self, module):
        self.original.exec_module(module)
        self.callback(module)


class HookFinder(importlib.abc.MetaPathFinder):
    def __init__(self, editor):
        self.editor = editor

    def find_spec(self, fullname, path=None, target=None):
        callbacks = {'library.sensors.sensors_custom': self.sensors}
        callbacks['library.display'] = self.display
        callbacks['library.stats'] = self.stats
        callbacks['library.config'] = self.config
        if self.editor:
            callbacks['tkinter'] = self.tkinter
        if fullname not in callbacks:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is not None and spec.loader is not None:
            spec.loader = HookLoader(spec.loader, callbacks[fullname])
        return spec

    @staticmethod
    def config(module):
        from .pages import install_config
        install_config(module)

    @staticmethod
    def sensors(module):
        from .core import register_sensors
        service = get_service()
        register_sensors(module, service.store)
        service.start()

    @staticmethod
    def display(module):
        if get_service().config.get('render', {}).get('batch_frames', False):
            from .rendering import install_display
            install_display(module)

    @staticmethod
    def stats(module):
        from .rendering import install_stats
        install_stats(module)

    @staticmethod
    def tkinter(module):
        original = module.Tk.__init__

        def initialize(root, *args, **kwargs):
            original(root, *args, **kwargs)
            from .editor import attach
            root.after(0, lambda: attach(root, get_service()))

        module.Tk.__init__ = initialize


def install():
    global _installed
    if _installed or not os.environ.get('TURZX_MQTT_CONFIG') or not os.environ.get('TURZX_UPSTREAM'):
        return
    upstream = Path(os.environ['TURZX_UPSTREAM']).resolve()
    entry = Path(sys.argv[0]).resolve()
    if entry.parent != upstream or entry.name not in ('main.py', 'theme-editor.py', 'configure.py'):
        return
    if not (upstream / 'library' / 'sensors' / 'sensors_custom.py').is_file():
        raise RuntimeError('TURZX_UPSTREAM does not point to the expected upstream project.')
    sys.meta_path.insert(0, HookFinder(editor=entry.name == 'theme-editor.py'))
    _installed = True
