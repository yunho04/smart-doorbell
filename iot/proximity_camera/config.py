import json
import math

DEFAULTS = {
    "trigger_bcm": 23, "echo_bcm": 24, "near_cm": 50, "far_cm": 70,
    "consecutive": 3, "cooldown_s": 5, "interval_s": 0.1,
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
    for key in ("near_cm", "far_cm", "cooldown_s", "interval_s", "echo_timeout_s", "camera_timeout_s", "camera_af_timeout_s", "camera_capture_timeout_s", "settle_s"):
        v = config[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise ValueError("invalid " + key)
    if not 2 <= config["near_cm"] < config["far_cm"] <= 400 or not 0 < config["echo_timeout_s"] <= 0.1 or config["interval_s"] < 0.06 or config["camera_timeout_s"] <= 0 or config["camera_af_timeout_s"] <= 0 or config["camera_capture_timeout_s"] <= 0:
        raise ValueError("invalid thresholds or timing")
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
    return config
