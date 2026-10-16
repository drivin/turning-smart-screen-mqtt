# SPDX-License-Identifier: GPL-3.0-or-later
import ast
import importlib.util
import math
import os
from pathlib import Path
import tempfile
import subprocess
import sys
from types import SimpleNamespace
import unittest

from mqtt_display.core import SensorStore, load_config, register_sensors
from mqtt_display.theme import save_widget

ROOT = Path(__file__).resolve().parents[1]


class SensorsTest(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / 'examples/mqtt.yaml')
        self.now = 10
        self.store = SensorStore(self.config['sensors'], clock=lambda: self.now)
        self.store.connected = True

    def message(self, value):
        self.store.ingest('example/bridge/health',
                          ('{"os":{"memory_percent":' + value + '}}').encode())

    def test_render_snapshot_and_shared_history(self):
        spec = importlib.util.spec_from_file_location('custom_test', ROOT / 'turing-smart-screen-python/library/sensors/sensors_custom.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        register_sensors(module, self.store)
        self.message('12.5')
        first = module.MqttBridgeMemory()
        self.message('22.5')
        second = module.MqttBridgeMemory()
        self.assertEqual(first.as_numeric(), 12.5)
        self.assertEqual(first.as_string(), '12.5%')
        self.assertEqual(second.last_values()[-2:], [12.5, 22.5])
        self.assertEqual(len(second.last_values()), 60)
        self.assertTrue(math.isnan(second.last_values()[0]))

    def test_invalid_payloads_do_not_poison_history_or_block_other_sensors(self):
        self.message('12.5')
        for payload in [b'not json', b'{"os":{}}', b'{"os":{"memory_percent":true}}', b'{"os":{"memory_percent":"NaN"}}']:
            self.store.ingest('example/bridge/health', payload)
            result = self.store.snapshot('MqttBridgeMemory')
            self.assertEqual(result.status, 'invalid')
            self.assertIsNone(result.number)
        self.assertEqual(list(self.store.history['MqttBridgeMemory']), [12.5])
        self.store.ingest('example/bridge/state', b'{"state":"online"}')
        self.assertEqual(self.store.snapshot('MqttBridgeStatus').text, 'online')

    def test_missing_stale_disconnect_and_recovery(self):
        self.assertEqual(self.store.snapshot('MqttBridgeMemory').status, 'missing')
        self.message('1')
        self.now += 3601
        self.assertEqual(self.store.snapshot('MqttBridgeMemory').status, 'stale')
        self.store.connected = False
        self.assertEqual(self.store.snapshot('MqttBridgeMemory').status, 'disconnected')
        self.store.connected = True
        self.message('2')
        self.assertEqual(self.store.snapshot('MqttBridgeMemory').number, 2)

    def test_registration_collision_is_atomic(self):
        module = SimpleNamespace(MqttBridgeMemory=object())
        with self.assertRaises(ValueError):
            register_sensors(module, self.store)
        self.assertFalse(hasattr(module, 'MqttBridgeStatus'))

    def test_byte_scaling_applies_to_value_text_and_history(self):
        definitions={'MqttRam':{'topic':'mem/used','kind':'number','scale':1/1024**3,
                                'unit':' GiB','decimals':1,'stale_after':60,'history':3}}
        store=SensorStore(definitions)
        store.connected=True
        store.ingest('mem/used',b'3221225472')
        result=store.snapshot('MqttRam')
        self.assertEqual(result.number,3)
        self.assertEqual(result.text,'3.0 GiB')
        self.assertEqual(result.history[-1],3)

    def test_actual_upstream_custom_render_dispatch(self):
        # Execute the actual upstream Custom class without initializing real hardware.
        source = ast.parse((ROOT / 'turing-smart-screen-python/library/stats.py').read_text(encoding='utf-8'))
        custom = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == 'Custom')
        spec = importlib.util.spec_from_file_location('custom_test', ROOT / 'turing-smart-screen-python/library/sensors/sensors_custom.py')
        sensors = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sensors)
        register_sensors(sensors, self.store)
        self.message('45')
        calls = []
        namespace = dict(math=math, sensors_custom=sensors,
                         config=SimpleNamespace(THEME_DATA={'STATS': {'CUSTOM': {'INTERVAL': 1,
                             'MqttBridgeMemory': {'TEXT': {}, 'GRAPH': {}, 'LINE_GRAPH': {}}}}}),
                         logger=SimpleNamespace(error=lambda msg: self.fail(msg)))
        for name in ['display_themed_value', 'display_themed_progress_bar', 'display_themed_line_graph']:
            namespace[name] = lambda **kwargs: calls.append(kwargs)
        exec(compile(ast.Module(body=[custom], type_ignores=[]), '<upstream Custom>', 'exec'), namespace)
        namespace['Custom'].stats()
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0]['value'], '45.0%')
        self.assertEqual(calls[1]['value'], 45)
        self.assertEqual(calls[2]['values'][-1], 45)


class ThemeTest(unittest.TestCase):
    def test_saves_only_selected_page(self):
        import yaml
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'theme.yaml'
            data={'STATS':{'CUSTOM':{'INTERVAL':10}},'MQTT_PAGES':{'INTERVAL':20,'VIEWS':[
                {'CUSTOM':{'MqttCpu':{'TEXT':{'Y':122}}}},
                {'CUSTOM':{'MqttRx':{'TEXT':{'Y':213}}}}]}}
            path.write_text(yaml.safe_dump(data),encoding='utf-8')
            save_widget(path,'MqttRx','TEXT',{'Y':215},page=1)
            saved=yaml.safe_load(path.read_text(encoding='utf-8'))
            self.assertEqual(saved['MQTT_PAGES']['VIEWS'][0],data['MQTT_PAGES']['VIEWS'][0])
            self.assertEqual(saved['MQTT_PAGES']['VIEWS'][1]['CUSTOM']['MqttRx']['TEXT']['Y'],215)
            self.assertEqual(saved['STATS'],data['STATS'])

    def test_save_preserves_comments_existing_widgets_and_creates_exact_backup(self):
        original = '# user theme\nSTATS:\n  CUSTOM:\n    INTERVAL: 3\n    Existing:\n      TEXT: {SHOW: true}\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'theme.yaml'
            path.write_text(original, encoding='utf-8')
            backup = save_widget(path, 'MqttBridgeMemory', 'TEXT', {'SHOW': True, 'X': 5})
            self.assertEqual(backup.read_text(encoding='utf-8'), original)
            self.assertIn('# user theme', path.read_text(encoding='utf-8'))
            import yaml
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
            self.assertEqual(data['STATS']['CUSTOM']['INTERVAL'], 3)
            self.assertIn('Existing', data['STATS']['CUSTOM'])
            save_widget(path, 'MqttBridgeMemory', 'GRAPH', {'SHOW': True})
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
            self.assertIn('TEXT', data['STATS']['CUSTOM']['MqttBridgeMemory'])
            self.assertIn('GRAPH', data['STATS']['CUSTOM']['MqttBridgeMemory'])


class FrameBatchTest(unittest.TestCase):
    def test_counter_rates_wait_reset_and_reconnect_gap(self):
        now=[0]
        store=SensorStore({'MqttRx':{'topic':'rx','kind':'number','rate':True,
                          'scale':1/1024**2,'unit':' MiB/s','stale_after':60}},clock=lambda:now[0])
        store.connected=True
        store.ingest('rx',b'1048576')
        self.assertEqual(store.snapshot('MqttRx').status,'warming')
        now[0]=10
        store.ingest('rx',b'22020096')
        self.assertEqual(store.snapshot('MqttRx').number,2)
        now[0]=20
        store.ingest('rx',b'0')
        self.assertEqual(store.snapshot('MqttRx').status,'warming')
        now[0]=100
        store.ingest('rx',b'1048576')
        self.assertEqual(store.snapshot('MqttRx').status,'warming')

    def test_pages_follow_deadlines_and_reload_without_mixing_content(self):
        from mqtt_display.pages import Pages
        import copy
        now=[0]
        pages=Pages(clock=lambda:now[0])
        theme={'STATS':{},'MQTT_PAGES':{'INTERVAL':20,'VIEWS':[
            {'static_text':{'a':{}},'CUSTOM':{'one':{}}},
            {'static_text':{'b':{}},'CUSTOM':{'two':{}}}]}}
        config=SimpleNamespace(THEME_DATA=copy.deepcopy(theme))
        self.assertTrue(pages.apply(config))
        now[0]=19
        self.assertFalse(pages.apply(config))
        now[0]=20
        self.assertTrue(pages.apply(config))
        self.assertEqual(set(config.THEME_DATA['STATS']['CUSTOM']),{'two'})
        config.THEME_DATA=copy.deepcopy(theme)
        self.assertFalse(pages.apply(config))
        self.assertEqual(set(config.THEME_DATA['static_text']),{'b'})
        now[0]=40
        self.assertTrue(pages.apply(config))
        self.assertEqual(set(config.THEME_DATA['STATS']['CUSTOM']),{'one'})

    def test_combines_regions_into_single_transfer_and_rolls_back_failed_frame(self):
        from PIL import Image
        from mqtt_display.rendering import FrameBatch
        class Lcd:
            def __init__(self):
                self.current_state=Image.new('RGB',(10,5),'black')
                self.sent=[]
            def get_width(self): return 10
            def get_height(self): return 5
            def DisplayPILImage(self,image,x=0,y=0,image_width=0,image_height=0):
                self.current_state.paste(image,(x,y))
                self.sent.append(self.current_state.copy())
        lcd=Lcd();batch=FrameBatch(lcd)
        with batch.frame():
            lcd.DisplayPILImage(Image.new('RGB',(3,3),'red'),1,1)
            with batch.frame():
                lcd.DisplayPILImage(Image.new('RGB',(2,2),'blue'),7,0)
        self.assertEqual(len(lcd.sent),1)
        self.assertEqual(lcd.sent[0].getpixel((1,1)),(255,0,0))
        self.assertEqual(lcd.sent[0].getpixel((7,0)),(0,0,255))
        before=lcd.current_state.tobytes()
        with self.assertRaises(ValueError):
            with batch.frame():
                lcd.DisplayPILImage(Image.new('RGB',(10,5),'white'))
                raise ValueError('bad widget')
        self.assertEqual(lcd.current_state.tobytes(),before)
        self.assertEqual(len(lcd.sent),1)


class StartupTest(unittest.TestCase):
    def test_normal_python_entrypoint_loads_sensors_only_in_configured_checkout(self):
        import yaml
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            sensor_file = base / 'library/sensors/sensors_custom.py'
            sensor_file.parent.mkdir(parents=True)
            sensor_file.write_bytes((ROOT / 'turing-smart-screen-python/library/sensors/sensors_custom.py').read_bytes())
            config = load_config(ROOT / 'examples/mqtt.yaml')
            config['broker'] = {'host': '127.0.0.1', 'port': 9, 'tls': False}
            config_path = base / 'mqtt.yaml'
            config_path.write_text(yaml.safe_dump(config), encoding='utf-8')
            source = ('import library.sensors.sensors_custom as custom\n'
                      'print(hasattr(custom, "MqttBridgeMemory"))\n')
            main = base / 'main.py'
            main.write_text(source, encoding='utf-8')
            other = base / 'other.py'
            other.write_text(source, encoding='utf-8')
            env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / 'bootstrap'), str(ROOT)]),
                       TURZX_UPSTREAM=str(base), TURZX_MQTT_CONFIG=str(config_path))
            enabled = subprocess.run([sys.executable, str(main)], env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(enabled.returncode, 0, enabled.stderr)
            self.assertEqual(enabled.stdout.strip(), 'True', enabled.stderr)
            disabled = subprocess.run([sys.executable, str(other)], env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(disabled.returncode, 0, disabled.stderr)
            self.assertEqual(disabled.stdout.strip(), 'False', disabled.stderr)


if __name__ == '__main__':
    unittest.main()
