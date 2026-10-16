# MQTT extension setup

The extension adds live MQTT sensors to the original theme editor and runtime
without changing upstream Python source. New installations and CI use upstream
`main`. The extension uses internal upstream interfaces, so CI checks integration
behavior when builds run.

## Installation

Install Python 3.14, clone this extension, and run these commands from its root:

```sh
git clone --branch main https://github.com/mathoudebine/turing-smart-screen-python.git turing-smart-screen-python
python -m venv .venv
```

Activate the virtual environment, then install dependencies:

```sh
python -m pip install -r requirements-extension.txt -r turing-smart-screen-python/requirements.txt
```

Copy `examples/themes/MqttClusterRetro92` into the upstream checkout's
`res/themes` directory. Adapt the broker and sensor topics in
`examples/cluster-mqtt.yaml`. Its hostname `mqtt.example.com` is a placeholder.
Keep local credentials in environment variables, not in YAML or source files.

## Starting the editor

Example PowerShell configuration, from the extension root:

```powershell
$mqttRoot = (Get-Location).Path
$env:PYTHONPATH = "$mqttRoot\bootstrap;$mqttRoot"
$env:TURZX_UPSTREAM = "$mqttRoot\turing-smart-screen-python"
$env:TURZX_MQTT_CONFIG = "$mqttRoot\examples\cluster-mqtt.yaml"
$env:TURZX_MQTT_USER = 'YOUR_MQTT_USER'
$mqttSecret = Read-Host 'MQTT password' -AsSecureString
$env:TURZX_MQTT_PASSWORD = [System.Net.NetworkCredential]::new('', $mqttSecret).Password
$mqttSecret = $null
Set-Location $env:TURZX_UPSTREAM
& "$mqttRoot\.venv\Scripts\python.exe" theme-editor.py MqttClusterRetro92
```

On Linux/macOS use the same environment variables with absolute paths, and
separate the two `PYTHONPATH` entries with `:`. Start
`python theme-editor.py MqttClusterRetro92` from the upstream directory. The integration uses
`bootstrap/sitecustomize.py`; copying `mqtt_display` alone is insufficient.

The selection window displays live sensor values. Choose text/number, bar,
history graph or pie chart, adjust its settings, and save. Existing widgets of
the same sensor/type are updated. Each save creates a theme backup. **Ctrl+M**
reopens the window. In multi-page themes, saves affect the currently visible page.

## Sensor definitions

Each sensor needs a Python identifier starting with `Mqtt`, an exact MQTT topic,
`kind: number` or `kind: text`, and a positive `stale_after` in seconds. Wildcard
subscriptions are not supported. `path` selects JSON keys or array indices;
omit it for scalar payloads. Optional `unit`, `decimals`, `history` and `scale`
control formatting and numeric conversion.

`rate: true` derives a numeric rate from a cumulative counter. Use
`scale: 0.00000095367431640625` to convert byte/s to MiB/s. The first measurement,
a reset counter, reconnect or long sampling gap requires a fresh measurement
pair. Rates represent the average over the last received measurement interval.

The client only subscribes; it does not publish. Configure TLS and the broker's
port explicitly. Missing, invalid, disconnected and stale readings display text
status. Numeric widgets do not receive replacement values on failure, so an old
bar can remain visible until a valid reading returns. History is in memory only.

## Included theme

The retro example shows three nodes, with CPU, memory, RootFS and optional USB
disks on the hardware page, and parent-NIC RX/TX plus link speed on the network
page. Node names, interfaces, disk mounts and topics are examples to customize.
`MQTT_PAGES.INTERVAL: 20` controls page switching. Both pages use the same image.
The background and its generation prompt are included in the theme directory.

Use identical sensor IDs on the editor and runtime. Copy edited themes with all
image assets to the runtime. See [Docker setup](docker/README.md) for USB access,
Compose configuration and container builds.

## Validation

From the extension root, with the virtual environment active:

```sh
python -m unittest discover -s tests
python -m mqtt_display --config examples/cluster-mqtt.yaml --seconds 25
python tools/smoke_editor.py --theme-dir examples/themes/MqttClusterRetro92 --mqtt-config examples/cluster-mqtt.yaml --demo
python tools/build_theme_preview.py
```

Live checks require the configured broker credentials. `--demo` uses fixed sample
readings without connecting to a broker or reading credentials. The GUI smoke test uses
an isolated upstream copy under `artifacts/editor-smoke` and a simulated panel.
It saves previews of both pages without modifying upstream source or a physical
display. The preview builder creates the README GIF from those renders.
