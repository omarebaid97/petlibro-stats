import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("petlibro-stats")

EMAIL = os.environ["PETLIBRO_EMAIL"]
PASSWORD = os.environ["PETLIBRO_PASSWORD"]
REGION = os.environ.get("PETLIBRO_REGION", "US")
TIMEZONE = os.environ.get("PETLIBRO_TIMEZONE", "America/Chicago")
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))
STATS_TOKEN = os.environ.get("STATS_TOKEN", "")
PORT = int(os.environ.get("PORT", "8080"))

API_URLS = {"US": "https://api.us.petlibro.com"}
APP_ID = 1
APP_SN = "c35772530d1041699c87fe62348507a8"


class PetLibroError(Exception):
    pass


class PetLibroClient:
    def __init__(self, email, password, region, tz):
        self.email = email
        self.password_hash = hashlib.md5(password.encode("utf-8")).hexdigest()
        self.region = region
        self.base_url = API_URLS.get(region, API_URLS["US"])
        self.tz = tz
        self.token = None
        self.session = requests.Session()
        self.session.headers.update({
            "source": "ANDROID",
            "language": "EN",
            "timezone": tz,
            "version": "1.3.45",
            "Content-Type": "application/json",
        })

    def login(self):
        resp = self.session.post(f"{self.base_url}/member/auth/login", json={
            "appId": APP_ID,
            "appSn": APP_SN,
            "country": self.region,
            "email": self.email,
            "password": self.password_hash,
            "phoneBrand": "",
            "phoneSystemVersion": "",
            "timezone": self.tz,
            "thirdId": None,
            "type": None,
        }, timeout=15)
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise PetLibroError(f"login failed: {body.get('msg')}")
        self.token = body["data"]["token"]
        self.session.headers["token"] = self.token
        log.info("logged in as %s", self.email)

    def _post(self, path, payload, retry=True):
        if not self.token:
            self.login()
        resp = self.session.post(f"{self.base_url}{path}", json=payload, timeout=15)
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") == 1009 and retry:
            log.info("token expired, re-logging in")
            self.token = None
            self.login()
            return self._post(path, payload, retry=False)
        if body.get("code") != 0:
            raise PetLibroError(f"{path} failed: code={body.get('code')} msg={body.get('msg')}")
        return body.get("data")

    def list_devices(self):
        return self._post("/device/device/list", {}) or []

    def grain_status(self, serial):
        return self._post("/device/data/grainStatus", {"id": serial, "deviceSn": serial})


# Order devices in the output: feeders, then fountain, then litter box.
TYPE_ORDER = {"Feeder": 0, "Fountain": 1, "Smart Litter Box": 2}


def device_type(dev):
    return dev.get("secondCategoryNameI18n") or "Other"


def common_fields(dev):
    serial = dev.get("deviceSn")
    return {
        "serial": serial,
        "type": device_type(dev),
        "name": dev.get("name"),
        "model": dev.get("productName"),
        "product_code": dev.get("productIdentifier"),
        "online": dev.get("online"),
        "battery_percent": dev.get("electricQuantity"),
        "battery_state": dev.get("batteryState"),
        "wifi_rssi": dev.get("wifiRssi"),
        "error": bool(dev.get("errorState"))
        or dev.get("doorErrorState") not in (None, "NORMAL")
        or bool(dev.get("deviceStoppedWorking")),
        "error_message": dev.get("exceptionMessage") or None,
    }


def build_feeder(client, dev):
    entry = common_fields(dev)
    entry.update({
        "food_level_percent": dev.get("weightPercent"),
        "food_level_state": dev.get("weightState"),
        "next_feeding_time": dev.get("nextFeedingTime"),
        "next_feeding_cups": dev.get("nextFeedingQuantity"),
        "desiccant_state": dev.get("desiccantState"),
        "today_feeding_times": None,
        "today_feeding_cups": None,
    })
    try:
        grain = client.grain_status(entry["serial"]) or {}
        entry["today_feeding_times"] = grain.get("todayFeedingTimes")
        entry["today_feeding_cups"] = grain.get("todayFeedingQuantity")
    except Exception as e:
        log.warning("grainStatus failed for %s: %s", entry["serial"], e)
    return entry


def build_fountain(dev):
    entry = common_fields(dev)
    entry.update({
        "water_level_percent": dev.get("weightPercent"),
        "water_level_state": dev.get("weightState"),
        "today_water_ml": dev.get("todayTotalMl"),
        "remaining_filter_days": dev.get("remainingReplacementDays"),
        "remaining_cleaning_days": dev.get("remainingCleaningDays"),
    })
    return entry


def build_litter_box(dev):
    entry = common_fields(dev)
    entry.update({
        "waste_bin_full": dev.get("rubbishFullState"),
        "waste_bin_in_place": dev.get("rubbishInplaceState"),
        "filter_state": dev.get("filterState"),
        "clean_state": dev.get("cleanState"),
        "mat_state": dev.get("matState"),
        "remaining_mat_days": dev.get("remainingMatDays"),
        "remaining_cleaning_days": dev.get("remainingCleaningDays"),
        "remaining_sand_days": dev.get("remainingReplacementDays"),
        "door_state": dev.get("doorState"),
        "deodorizer_on": dev.get("deodorizationStateOn"),
    })
    return entry


def build_other(dev):
    entry = common_fields(dev)
    entry["raw"] = dev
    return entry


def build_snapshot(client):
    devices = client.list_devices()
    devices.sort(key=lambda d: TYPE_ORDER.get(device_type(d), 99))

    devices_out = []
    for dev in devices:
        t = device_type(dev)
        if t == "Feeder":
            devices_out.append(build_feeder(client, dev))
        elif t == "Fountain":
            devices_out.append(build_fountain(dev))
        elif t == "Smart Litter Box":
            devices_out.append(build_litter_box(dev))
        else:
            devices_out.append(build_other(dev))

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "device_count": len(devices_out),
        "devices": devices_out,
    }


_lock = threading.Lock()
_latest = {"updated_at": None, "device_count": 0, "devices": [], "error": "not polled yet"}


def poll_loop():
    global _latest
    client = PetLibroClient(EMAIL, PASSWORD, REGION, TIMEZONE)
    while True:
        try:
            snapshot = build_snapshot(client)
            with _lock:
                _latest = snapshot
            log.info("poll ok: %d device(s)", snapshot["device_count"])
        except Exception as e:
            log.error("poll failed: %s", e)
            with _lock:
                _latest = {**_latest, "error": str(e), "updated_at": datetime.now(timezone.utc).isoformat()}
        time.sleep(POLL_INTERVAL_SECONDS)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.info("%s - %s", self.client_address[0], fmt % args)

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._json(200, {"ok": True})
            return
        if parsed.path == "/stats":
            if STATS_TOKEN:
                qs = parse_qs(parsed.query)
                if qs.get("token", [None])[0] != STATS_TOKEN:
                    self._json(403, {"error": "forbidden"})
                    return
            with _lock:
                self._json(200, _latest)
            return
        self._json(404, {"error": "not found"})


def main():
    threading.Thread(target=poll_loop, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log.info("listening on :%d", PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
