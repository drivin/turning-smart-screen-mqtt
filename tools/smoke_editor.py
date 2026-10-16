# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated GUI smoke test; creates artifacts only, never opens a real panel."""
import os
import argparse
from pathlib import Path
import runpy
import shutil
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
UPSTREAM = ROOT / 'turing-smart-screen-python'
TARGET = ROOT / 'artifacts' / 'editor-smoke'


def prepare(panel92=False, theme_dir=None):
    import yaml
    TARGET.mkdir(parents=True, exist_ok=True)
    shutil.copytree(UPSTREAM / 'library', TARGET / 'library', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(UPSTREAM / 'theme-editor.py', TARGET / 'theme-editor.py')
    for relative in ['res/themes/default.yaml', 'res/docs/error-in-theme.png',
                     'res/backgrounds/circular-mask.png',
                     'res/icons/monitor-icon-17865/64.png',
                     'res/fonts/roboto-mono/RobotoMono-Regular.ttf',
                     'res/fonts/roboto/Roboto-Black.ttf']:
        destination = TARGET / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(UPSTREAM / relative, destination)
    config = yaml.safe_load((UPSTREAM / 'config.yaml').read_text(encoding='utf-8'))
    config['config'].update(THEME='MqttSmoke', HW_SENSORS='STATIC')
    config['display']['REVISION'] = 'SIMU'
    (TARGET / 'config.yaml').write_text(yaml.safe_dump(config), encoding='utf-8')
    theme = TARGET / 'res/themes/MqttSmoke/theme.yaml'
    theme.parent.mkdir(parents=True, exist_ok=True)
    if theme_dir:
        shutil.copytree(Path(theme_dir).resolve(),theme.parent,dirs_exist_ok=True)
        return
    if panel92:
        shutil.copy2(ROOT / 'examples/themes/MqttTurzx92/theme.yaml', theme)
        return
    data = {'display': {'DISPLAY_ORIENTATION': 'landscape', 'DISPLAY_SIZE': '3.5"'},
            'static_images': {}, 'static_text': {}, 'STATS': {'CUSTOM': {'INTERVAL': 1}}}
    theme.write_text(yaml.safe_dump(data), encoding='utf-8')
    from mqtt_display.theme import save_widget
    for key, y in [('MqttBridgeStatus', 15), ('MqttBridgeMemory', 55),
                   ('MqttBridgeLoad', 95), ('MqttBridgeUptime', 135)]:
        save_widget(theme, key, 'TEXT', {'SHOW': True, 'X': 20, 'Y': y,
                    'WIDTH': 400, 'HEIGHT': 36, 'FONT_SIZE': 24})
    save_widget(theme, 'MqttBridgeMemory', 'GRAPH', {'SHOW': True, 'X': 20, 'Y': 180,
                'WIDTH': 200, 'HEIGHT': 30, 'MIN_VALUE': 0, 'MAX_VALUE': 100,
                'BAR_COLOR': '30, 130, 200'})
    save_widget(theme, 'MqttBridgeMemory', 'LINE_GRAPH', {'SHOW': True, 'X': 250, 'Y': 180,
                'WIDTH': 200, 'HEIGHT': 100, 'MIN_VALUE': 0, 'MAX_VALUE': 100,
                'LINE_COLOR': '30, 130, 200', 'BACKGROUND_COLOR': '245, 245, 245',
                'AXIS': False, 'AUTOSCALE': False})


def demo_service(config):
    """Deterministic cluster readings for public previews; no broker connection."""
    from mqtt_display.core import SensorStore
    now = [time.monotonic() - 10]
    store = SensorStore(config['sensors'], clock=lambda: now[0])
    samples = {
        'Cpu': [24, 48, 12], 'RamPercent': [50, 65, 35],
        'RamUsed': [4, 10.4, 5.6], 'RamFree': [4, 5.6, 10.4],
        'Root': [35, 52, 71], 'Usb1': [64, 64, 64], 'Usb2': [42, 42, 42],
        'Rx': [0.75, 2.5, 12.25], 'Tx': [0.2, 1.25, 4.75],
        'LinkSpeed': [1000, 1000, 1000],
    }
    payloads = {}
    for key, definition in config['sensors'].items():
        prefix = next((f'MqttNode{i}' for i in (1, 2, 3) if key.startswith(f'MqttNode{i}')), None)
        if prefix is None or key[len(prefix):] not in samples:
            raise ValueError('--demo requires the generic cluster sensor configuration.')
        index = int(prefix[-1])-1
        number = samples[key[len(prefix):]][index] / definition.get('scale', 1)
        if definition.get('rate'):
            store.ingest(definition['topic'], b'0')
            number *= 10
        payloads[definition['topic']] = str(number).encode()
    now[0] += 10
    for topic, payload in payloads.items():
        store.ingest(topic, payload)
    store.clock = time.monotonic
    store.connected = True
    store.status = 'Demo data (no broker)'
    return SimpleNamespace(config=config, store=store, start=lambda: None, stop=lambda: None)


def execute(mqtt_config=None, demo=False):
    os.environ['TURZX_UPSTREAM'] = str(TARGET)
    os.environ['TURZX_MQTT_CONFIG'] = str(Path(mqtt_config).resolve() if mqtt_config else ROOT / 'examples/mqtt.yaml')
    sys.argv = [str(TARGET / 'theme-editor.py'), 'MqttSmoke']
    sys.path.insert(0, str(TARGET))
    os.chdir(TARGET)
    from mqtt_display.bootstrap import install, get_service
    if demo:
        from mqtt_display import bootstrap
        from mqtt_display.core import load_config
        bootstrap._service = demo_service(load_config(os.environ['TURZX_MQTT_CONFIG']))
    install()
    import tkinter
    from PIL import ImageGrab
    # Prevent an external editor from opening during this scripted test.
    if hasattr(os, 'startfile'):
        os.startfile = lambda *a, **kw: None
    original = tkinter.Tk.__init__

    def initialize(root, *args, **kwargs):
        original(root, *args, **kwargs)

        def finish():
            try:
                main = sys.modules['__main__']
                panel = root._mqtt_panel
                store = get_service().store
                assert all(store.snapshot(key).status == 'ok' for key in store.definitions)
                assert not main.error_in_theme
                assert panel.last_error is None, panel.last_error
                if main.config.THEME_DATA.get('MQTT_PAGES'):
                    from mqtt_display.pages import controller
                    for index, name in [(0,'hardware-preview.png'),(1,'network-preview.png')]:
                        controller.started=controller.clock()-20*index
                        main.refresh_theme()
                        assert main.config.THEME_DATA['_MQTT_PAGE_INDEX']==index
                        main.display.lcd.screen_image.save(TARGET / name)
                # Exercise the graphical selection and save handler against the copy.
                numeric=next(key for key,d in store.definitions.items() if d['kind']=='number'
                             and key in main.config.THEME_DATA['STATS']['CUSTOM'])
                panel.tree.selection_set(numeric)
                panel.kind.set('Bar')
                panel.load_style()
                panel.fields['WIDTH'].set('210')
                panel.save()
                main.display.lcd.screen_image.save(TARGET / 'mqtt-preview.png')
                window = panel.window
                window.update_idletasks()
                if sys.platform == 'win32':
                    import ctypes
                    ctypes.windll.user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
                    ctypes.windll.user32.GetAncestor.restype = ctypes.c_void_p
                    hwnd = ctypes.windll.user32.GetAncestor(window.winfo_id(), 2)
                    ImageGrab.grab(window=hwnd).save(TARGET / 'mqtt-selection.png')
                print('GUI_SMOKE_OK: registered sensors, live preview, graphical save, screenshots', flush=True)
                code = 0
            except BaseException:
                import traceback
                traceback.print_exc()
                code = 1
            get_service().stop()
            root.destroy()
            main = sys.modules['__main__']
            main.display.lcd.webServer.shutdown()
            os._exit(code)

        if mqtt_config and 'cluster' in str(mqtt_config) and not demo:
            root.after(27000, finish)
        else:
            root.after(6500, finish)

    tkinter.Tk.__init__ = initialize
    runpy.run_path(str(TARGET / 'theme-editor.py'), run_name='__main__')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--panel92', action='store_true', help='Test the 9.2-inch example theme')
    parser.add_argument('--theme-dir', help='Copy a theme directory into the isolated test checkout')
    parser.add_argument('--mqtt-config', help='MQTT configuration for the selected theme')
    parser.add_argument('--demo', action='store_true', help='Use deterministic cluster demo data without MQTT credentials')
    args = parser.parse_args()
    prepare(panel92=args.panel92,theme_dir=args.theme_dir)
    execute(mqtt_config=args.mqtt_config,demo=args.demo)
