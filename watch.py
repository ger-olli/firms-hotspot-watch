
import csv
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from shapely.geometry import Point, Polygon

POLYGON = Polygon([
    (21.30252, 44.83812),
    (21.21291, 44.79014),
    (20.99648, 44.89789),
    (21.10188, 44.96886),
])

# Bounding box for FIRMS Area API: west,south,east,north
MINX, MINY, MAXX, MAXY = POLYGON.bounds
BBOX = f"{MINX},{MINY},{MAXX},{MAXY}"

MAP_KEY = os.environ.get("FIRMS_MAP_KEY")
if not MAP_KEY:
    print("ERROR: FIRMS_MAP_KEY is not set.", file=sys.stderr)
    sys.exit(2)

BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# Keep this list explicit so failures can be isolated per source.
SOURCES = [
    "VIIRS_NOAA21_NRT",
    "VIIRS_NOAA20_NRT",
    "VIIRS_SNPP_NRT",
    "MODIS_NRT",
    "LANDSAT_NRT",
]

LOOKBACK_DAYS = os.environ.get("FIRMS_LOOKBACK_DAYS", "3")
STATE_PATH = Path("data/seen.json")
STATUS_PATH = Path("data/status.json")
EVENTS_PATH = Path("data/events.jsonl")

def load_seen():
    if STATE_PATH.exists():
        try:
            return set(json.loads(STATE_PATH.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()

def save_seen(seen):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(sorted(seen), indent=2), encoding="utf-8")

def norm_key(row, source):
    return "|".join([
        source,
        row.get("latitude",""),
        row.get("longitude",""),
        row.get("acq_date",""),
        row.get("acq_time",""),
        row.get("frp",""),
    ])

def parse_float(v):
    try:
        return float(v)
    except Exception:
        return None

def parse_acq_datetime(row):
    """Return FIRMS acquisition time as aware UTC datetime when possible."""
    date = str(row.get("acq_date", "")).strip()
    time = str(row.get("acq_time", "")).strip().zfill(4)
    if not date or len(time) != 4 or not time.isdigit():
        return None
    try:
        return datetime.strptime(date + time, "%Y-%m-%d%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None

def fetch_source(source):
    url = f"{BASE}/{MAP_KEY}/{source}/{BBOX}/{LOOKBACK_DAYS}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    text = r.text.strip()
    if not text:
        return []
    return list(csv.DictReader(io.StringIO(text)))

def classify(row):
    frp = parse_float(row.get("frp"))
    conf = str(row.get("confidence","")).lower()

    score = 0
    if frp is not None:
        if frp >= 50:
            score += 2
        elif frp >= 10:
            score += 1

    if conf in {"high", "h"}:
        score += 2
    elif conf in {"nominal", "n", "medium", "m"}:
        score += 1
    else:
        try:
            c = float(conf)
            if c >= 80:
                score += 2
            elif c >= 50:
                score += 1
        except Exception:
            pass

    if score >= 3:
        return "high"
    if score >= 1:
        return "medium"
    return "low"

def main():
    seen = load_seen()
    now = datetime.now(timezone.utc)
    run = {
        "checked_at_utc": now.isoformat(),
        "polygon": list(POLYGON.exterior.coords),
        "bbox": BBOX,
        "lookback_days": int(LOOKBACK_DAYS),
        "sources": {},
        "new_hotspots": [],
        "errors": [],
    }

    all_new = []

    for source in SOURCES:
        try:
            rows = fetch_source(source)
        except Exception as e:
            run["sources"][source] = {"ok": False, "error": str(e)}
            run["errors"].append({"source": source, "error": str(e)})
            continue

        latest_returned = None
        for row in rows:
            dt = parse_acq_datetime(row)
            if dt is not None and (latest_returned is None or dt > latest_returned):
                latest_returned = dt

        inside = []
        latest_inside = None
        for row in rows:
            lat = parse_float(row.get("latitude"))
            lon = parse_float(row.get("longitude"))
            if lat is None or lon is None:
                continue
            if not POLYGON.contains(Point(lon, lat)) and not POLYGON.touches(Point(lon, lat)):
                continue

            dt = parse_acq_datetime(row)
            if dt is not None and (latest_inside is None or dt > latest_inside):
                latest_inside = dt

            key = norm_key(row, source)
            item = dict(row)
            item["source"] = source
            item["inside_polygon"] = True
            item["severity"] = classify(row)
            item["_key"] = key
            inside.append(item)

            # seen.json prevents historical hits in the 3-day window from
            # being reported more than once across workflow runs.
            if key not in seen:
                all_new.append(item)
                seen.add(key)

        run["sources"][source] = {
            "ok": True,
            "records_returned": len(rows),
            "inside_polygon": len(inside),
            "latest_measurement_utc": latest_returned.isoformat() if latest_returned else None,
            "latest_measurement_inside_polygon_utc": latest_inside.isoformat() if latest_inside else None,
        }

    run["new_hotspots"] = all_new
    run["new_hotspot_count"] = len(all_new)

    STATUS_PATH.write_text(json.dumps(run, indent=2), encoding="utf-8")
    save_seen(seen)

    if all_new:
        with EVENTS_PATH.open("a", encoding="utf-8") as f:
            for item in all_new:
                f.write(json.dumps({
                    "detected_by_workflow_at_utc": now.isoformat(),
                    **item,
                }) + "\n")

        summary = ["## New FIRMS hotspots inside polygon", ""]
        for h in all_new:
            summary.append(
                f"- **{h['source']}** — {h.get('acq_date','')} {h.get('acq_time','')} UTC "
                f"— `{h.get('latitude')}, {h.get('longitude')}` "
                f"— FRP `{h.get('frp','n/a')}` MW "
                f"— confidence `{h.get('confidence','n/a')}` "
                f"— severity **{h.get('severity')}**"
            )
        Path("data/summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
        print("\n".join(summary))
    else:
        Path("data/summary.md").write_text(
            f"## FIRMS hotspot watch\n\nNo new hotspots inside polygon at {now.isoformat()}.\n",
            encoding="utf-8",
        )
        print("No new hotspots inside polygon.")

if __name__ == "__main__":
    main()
