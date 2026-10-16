# SPDX-License-Identifier: GPL-3.0-or-later
"""Theme changes preserving YAML comments, with conflict checks and backups."""
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import shutil
import tempfile

from ruamel.yaml import YAML


def save_widget(path, sensor_id, kind, style, interval=1, page=None):
    if kind not in ('TEXT', 'GRAPH', 'LINE_GRAPH', 'RADIAL'):
        raise ValueError('Unknown widget type.')
    path = Path(path).resolve()
    original = path.read_bytes()
    yaml = YAML()
    data = yaml.load(original.decode('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Theme must be a YAML mapping.')
    if page is not None:
        custom = data['MQTT_PAGES']['VIEWS'][page].setdefault('CUSTOM', {})
    else:
        custom = data.setdefault('STATS', {}).setdefault('CUSTOM', {})
    if custom.get('INTERVAL', 0) <= 0:
        custom['INTERVAL'] = interval
    custom.setdefault(sensor_id, {})[kind] = style
    output = io.StringIO()
    yaml.dump(data, output)
    updated = output.getvalue().encode('utf-8')
    backup = path.with_name(path.name + '.bak-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    with backup.open('xb') as stream:
        stream.write(original)
    shutil.copystat(path, backup)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.yaml.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(updated)
        shutil.copystat(path, temporary)
        if path.read_bytes() != original:
            raise RuntimeError('Theme was modified externally while saving. Please try again.')
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return backup
