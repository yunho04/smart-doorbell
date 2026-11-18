import json
import ipaddress
from urllib.parse import urlsplit
import math

DEFAULTS = {
    "mqtt_host": None, "mqtt_port": 1883, "spring_base_url": None,
    "mqtt_client_id": None, "presence_interval_s": 2, "presence_ack_timeout_s": 2, "session_status_timeout_s": 2,
    "device_id": 1, "sensor_type": "MOTION", "connection_timeout_s": 10,
    "event_timeout_s": 10, "http_timeout_s": 10,
    "sensor_backend": "rpi_gpio", "trigger_bcm": 20, "echo_bcm": 16, "near_cm": 50, "far_cm": 70,
    "consecutive": 3, "cooldown_s": 5, "interval_s": 0.5, "sensor_settle_s": 0.2, "trigger_pulse_s": 0.01,
    "echo_timeout_s": 0.1, "output_dir": "captures", "max_files": 100,
    "max_total_bytes": 104857600, "max_file_bytes": 10485760,
    "min_free_bytes": 104857600, "camera_timeout_s": 20,
    "camera_af_timeout_s": 8, "camera_capture_timeout_s": 8, "settle_s": 1,
    "camera_width": 1280, "camera_height": 720,
    "mock_readings": [100, 45, 40, 35, 30, "error", 80, 80, 80, 45, 40, 35],
}


def load_config(path=None):
    config = DEFAULTS.copy()
    if path:
        with open(path, encoding="utf-8") as f:
            supplied = json.load(f)
        if not isinstance(supplied, dict) or set(supplied) - set(config):
            raise ValueError("config must be an object with known keys")
        config.update(supplied)
    for key in ("near_cm", "far_cm", "cooldown_s", "interval_s", "echo_timeout_s", "sensor_settle_s", "trigger_pulse_s", "camera_timeout_s", "camera_af_timeout_s", "camera_capture_timeout_s", "settle_s"):
        v = config[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise ValueError("invalid " + key)
    if not 2 <= config["near_cm"] < config["far_cm"] <= 400 or not 0 < config["echo_timeout_s"] <= 0.1 or config["interval_s"] < 0.06 or config["camera_timeout_s"] <= 0 or config["camera_af_timeout_s"] <= 0 or config["camera_capture_timeout_s"] <= 0:
        raise ValueError("invalid thresholds or timing")
    if config["sensor_backend"] not in ("rpi_gpio", "lgpio"):
        raise ValueError("invalid sensor_backend")
    if not 0.00001 <= config["trigger_pulse_s"] <= 0.01:
        raise ValueError("invalid sensor timing")
    for key in ("trigger_bcm", "echo_bcm", "consecutive", "max_files", "max_total_bytes", "max_file_bytes", "min_free_bytes", "camera_width", "camera_height"):
        v = config[key]
        if isinstance(v, bool) or not isinstance(v, int) or v < (0 if key in ("trigger_bcm", "echo_bcm", "min_free_bytes") else 1):
            raise ValueError("invalid " + key)
    if config["trigger_bcm"] == config["echo_bcm"] or max(config["trigger_bcm"], config["echo_bcm"]) > 27:
        raise ValueError("invalid BCM pins")
    if not isinstance(config["output_dir"], str) or not config["output_dir"].strip():
        raise ValueError("invalid output_dir")
    if not isinstance(config["mock_readings"], list):
        raise ValueError("mock_readings must be a list")
    for value in config["mock_readings"]:
        if value == "error":
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 2 <= value <= 400:
            raise ValueError("invalid mock reading")
    for key in ("connection_timeout_s", "event_timeout_s", "http_timeout_s"):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 120:
            raise ValueError("invalid " + key)
    for key, maximum in (("device_id", 2**63 - 1), ("mqtt_port", 65535)):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
            raise ValueError("invalid " + key)
    if not isinstance(config["sensor_type"], str) or not config["sensor_type"].strip() or len(config["sensor_type"]) > 64:
        raise ValueError("invalid sensor_type")
    client_id = config["mqtt_client_id"]
    if client_id is not None and (not isinstance(client_id, str) or not client_id.strip() or len(client_id.encode("utf-8")) > 128 or any(ord(c) < 32 or ord(c) == 127 for c in client_id)):
        raise ValueError("invalid mqtt_client_id")
    for key in ("presence_interval_s", "presence_ack_timeout_s", "session_status_timeout_s"):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value < 10:
            raise ValueError("invalid " + key)
    if config["mqtt_host"] is not None:
        try:
            if not isinstance(config["mqtt_host"], str):
                raise ValueError()
            ipaddress.ip_address(config["mqtt_host"])
        except (ValueError, TypeError):
            raise ValueError("mqtt_host must be a numeric IP address")
    if config["spring_base_url"] is not None:
        try:
            if not isinstance(config["spring_base_url"], str):
                raise ValueError()
            url = urlsplit(config["spring_base_url"])
            if url.scheme not in ("http", "https") or not url.hostname or url.username is not None or url.password is not None or url.path not in ("", "/") or url.query or url.fragment:
                raise ValueError()
            ipaddress.ip_address(url.hostname)
            if url.port is not None and not 0 < url.port <= 65535:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("spring_base_url must be an HTTP(S) origin with numeric IP")
    return config


def validate_spring_config(config):
    if not config["mqtt_host"] or not config["spring_base_url"]:
        raise ValueError("--spring requires mqtt_host and spring_base_url")
    if (config["presence_interval_s"] + config["presence_ack_timeout_s"] + config["interval_s"] +
            config["sensor_settle_s"] + 2 * config["echo_timeout_s"] + config["trigger_pulse_s"] >= 10):
        raise ValueError("presence timing exceeds session window")
