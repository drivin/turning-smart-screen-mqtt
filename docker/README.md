# Docker runtime for TURZX 9.2-inch displays

The runtime combines unchanged upstream code with the separate MQTT extension.
It supports the TURZX USB device family `1cbe:0092`, using `REVISION: TUR_USB`.
The panel is natively 1920 x 462 pixels; the upstream theme canvas is 1920 x 480.

## Configuration

1. Check out upstream `main` into `turing-smart-screen-python` at the extension root.
2. Adapt `examples/cluster-mqtt-runtime.yaml` to your broker and topics.
3. Adjust `examples/runtime-turzx92.yaml` for your panel and theme.
4. Set `TURZX_DOCKER_NETWORK` to an existing Docker network that can reach your broker.

Replace the placeholder `mqtt.example.com` with your broker's hostname as resolved
from the selected Docker network. Credentials come from environment variables
and are not stored in the image. No host, network, username or USB device path
is selected automatically.

Find the panel on the Docker host:

```sh
lsusb -d 1cbe:0092
```

Use its actual device path in place of `/dev/bus/usb/BBB/DDD`:

```bash
export TURZX_USB_DEVICE=/dev/bus/usb/BBB/DDD
export TURZX_MQTT_USER=YOUR_MQTT_USER
export TURZX_DOCKER_NETWORK=YOUR_EXISTING_DOCKER_NETWORK
read -rsp 'MQTT password: ' TURZX_MQTT_PASSWORD; echo
export TURZX_MQTT_PASSWORD

docker compose -f docker/compose.yaml config --quiet
docker compose -f docker/compose.yaml up -d --build
docker compose -f docker/compose.yaml logs -f runtime
```

The Compose file mounts the runtime configuration, MQTT definitions and theme
read-only. It passes through only the selected USB device. Recheck its path after
unplugging and reconnecting the panel. The runtime starts with `python main.py`;
the editor runs separately on your desktop.

## Theme and Telegraf

`MqttClusterRetro92` shows three example nodes with hardware and network views,
switching every 20 seconds. It includes CPU and memory bars, disk pies, and RX/TX
in MiB/s. Adapt the sensor topics and disk/interface names to your systems.
The runtime example rotates the panel output by 180 degrees.
The node names `node1` to `node3`, `eth0` interfaces, `/mnt/usb1` and `/mnt/usb2`
mounts, and `example/cluster/...` topics are illustrative placeholders. They do
not describe or automatically discover your hosts. Use the theme generator only
to recreate these public examples; it overwrites their YAML files.

CPU topics expect Telegraf's `usage_active` field (`report_active = true`).
Network topics contain cumulative byte counters; the extension derives rates
from successive readings. In containerized Telegraf installations, verify that
network statistics describe the host rather than the container namespace.
`tools/telegraf-parent-net.sh` is an optional read-only input helper for deployments
that already mount the host filesystem at `/hostfs`. Install it at a path of your
choice and configure a Telegraf `inputs.exec` command with `data_format = "influx"`.
It reads `/hostfs/proc/1/net/dev` and physical NICs under `/hostfs/sys/class/net`.

`render.batch_frames: true` combines widget drawing into one USB frame on the
TURZX driver. Transfers can take several seconds; the theme schedules updates
every ten seconds. Other drivers retain their existing rendering behavior.

## Published images

The GitHub Actions workflow builds Linux AMD64 and ARM64 images from upstream
`main` and publishes to `ghcr.io/<owner>/<repository>`. Use the package's actual
image name and tag when replacing the local Compose `build` configuration with
an `image` reference. See the [project README](../README.md) for publishing rules.
