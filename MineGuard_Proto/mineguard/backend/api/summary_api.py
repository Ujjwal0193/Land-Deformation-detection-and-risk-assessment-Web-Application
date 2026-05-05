"""summary_api.py — FastAPI router for rule-based InSAR analysis summary (Page 8).

Reads the processed results CSV and config files to generate a structured
geotechnical summary without any external AI API.

Endpoints:
  GET /api/summary/generate  — Generate (or return cached) summary
  DELETE /api/summary/cache  — Clear cached summary to force regeneration
"""

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException

from shared.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/summary", tags=["Summary"])

RESULTS_DIR   = PROJECT_ROOT / "results"
HOTSPOTS_FILE = PROJECT_ROOT / "config" / "hotspots.json"
CONFIG_FILE   = PROJECT_ROOT / "config" / "config.yaml"
REPORT_CSV    = RESULTS_DIR / "advanced_hotspot_report.csv"
SUMMARY_CACHE = RESULTS_DIR / "summary_cache.json"


# ── Risk thresholds (mm) ──────────────────────────────────────────────────────
# Based on standard geotechnical InSAR monitoring criteria for mining sites.

def _risk_level(vert_mm: float, ew_mm: float) -> str:
    av, ae = abs(vert_mm), abs(ew_mm)
    if av > 300 or ae > 300:
        return "CRITICAL"
    if av > 150 or ae > 200:
        return "HIGH"
    if av > 75 or ae > 100:
        return "MEDIUM"
    return "LOW"


# ── CSV parser ────────────────────────────────────────────────────────────────

def _parse_csv() -> Tuple[Dict[str, Dict], Dict[str, List]]:
    """
    Returns:
        cumulative  — {label: {vertical_mm, ew_mm, epochs: [...]}}
        single_orbit — {label: [rows]}   (single-orbit LOS rows, fallback)
    """
    if not REPORT_CSV.exists():
        return {}, {}

    cumulative: Dict[str, Dict] = {}
    single_orbit: Dict[str, List] = {}
    in_decomp = False

    with open(REPORT_CSV, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Section header
        if "2D VECTOR DECOMPOSITION" in stripped:
            in_decomp = True
            continue
        if stripped.startswith("hotspot,") or stripped.startswith("---"):
            continue

        parts = [p.strip() for p in stripped.split(",")]

        if in_decomp:
            # hotspot, approx_date, true_vertical_mm, east_west_mm, ...
            if len(parts) < 4:
                continue
            label = parts[0]
            try:
                v = float(parts[2])
                ew = float(parts[3])
                date = parts[1]
            except ValueError:
                continue
            if label not in cumulative:
                cumulative[label] = {"vertical_mm": 0.0, "ew_mm": 0.0, "epochs": []}
            cumulative[label]["vertical_mm"] += v
            cumulative[label]["ew_mm"] += ew
            cumulative[label]["epochs"].append({"date": date, "v": v, "ew": ew})
        else:
            # hotspot, px, py, master, slave, orbit, los, vert_approx, gradient, bearing, dir, inc
            if len(parts) < 8:
                continue
            label = parts[0]
            try:
                los = float(parts[6])
                vert = float(parts[7])
                gradient = float(parts[8]) if len(parts) > 8 else 0.0
                flow_dir = parts[10] if len(parts) > 10 else "?"
                orbit = parts[5]
                master = parts[3]
                slave = parts[4]
            except ValueError:
                continue
            if label not in single_orbit:
                single_orbit[label] = []
            single_orbit[label].append({
                "master": master, "slave": slave,
                "orbit": orbit, "los": los, "vert": vert,
                "gradient": gradient, "flow_dir": flow_dir,
            })

    return cumulative, single_orbit


def _read_hotspots() -> List[Dict[str, Any]]:
    if not HOTSPOTS_FILE.exists():
        return []
    with open(HOTSPOTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_site_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    if not CONFIG_FILE.exists():
        return cfg
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s.startswith("lat:"):
                cfg["lat"] = s.split(":", 1)[1].strip()
            elif s.startswith("lon:"):
                cfg["lon"] = s.split(":", 1)[1].strip()
            elif s.startswith("start_date:"):
                cfg["start_date"] = s.split(":", 1)[1].strip().strip("'")
            elif s.startswith("end_date:"):
                cfg["end_date"] = s.split(":", 1)[1].strip().strip("'")
    return cfg


# ── Sentence generators ───────────────────────────────────────────────────────

_RISK_DESCRIPTION = {
    "LOW":      "minor",
    "MEDIUM":   "moderate",
    "HIGH":     "significant",
    "CRITICAL": "severe and potentially hazardous",
}

_DIRECTION_TEXT = {
    "N": "northward", "NE": "north-eastward", "E": "eastward", "SE": "south-eastward",
    "S": "southward", "SW": "south-westward", "W": "westward", "NW": "north-westward",
}


def _hotspot_sentence(label: str, vert: float, ew: float, risk: str,
                      epochs: List[Dict]) -> str:
    """Generate one readable sentence summarising a hotspot."""
    vert_dir = "subsidence" if vert < 0 else "uplift"
    ew_dir   = "eastward"  if ew  > 0 else "westward"
    desc     = _RISK_DESCRIPTION[risk]

    # Detect dominant motion
    if abs(vert) >= abs(ew) * 1.5:
        motion = f"predominantly vertical {vert_dir} of {abs(vert):.0f} mm"
    elif abs(ew) >= abs(vert) * 1.5:
        motion = f"predominantly lateral {ew_dir} motion of {abs(ew):.0f} mm"
    else:
        motion = (f"combined {vert_dir} of {abs(vert):.0f} mm and "
                  f"{ew_dir} shift of {abs(ew):.0f} mm")

    # Detect sharp single-epoch event
    event_note = ""
    if epochs:
        max_ep = max(epochs, key=lambda e: abs(e["v"]))
        if abs(max_ep["v"]) > 100:
            event_note = (f" A sharp displacement of {max_ep['v']:.0f} mm vertical "
                          f"was recorded in the {max_ep['date']} epoch.")

    return (f"Hotspot {label} exhibits {desc} {motion} "
            f"over the full monitoring period.{event_note}")


def _detect_critical_events(cumulative: Dict, single_orbit: Dict) -> str:
    """Identify the most significant displacement events across all hotspots."""
    events = []

    for label, data in cumulative.items():
        for ep in data.get("epochs", []):
            if abs(ep["v"]) > 120:
                events.append((label, ep["date"], ep["v"], "vertical"))
            if abs(ep["ew"]) > 150:
                events.append((label, ep["date"], ep["ew"], "E–W"))

    if not events:
        # Check single-orbit for large single-epoch LOS
        for label, rows in single_orbit.items():
            for r in rows:
                if abs(r["los"]) > 200:
                    events.append((label, f"{r['master']}→{r['slave']}", r["los"], "LOS"))

    if not events:
        return ("No extreme single-epoch displacement events were identified. "
                "Deformation appears to be gradual and progressive across the monitoring period.")

    # Sort by magnitude
    events.sort(key=lambda x: abs(x[2]), reverse=True)
    top = events[:3]
    parts = [
        f"Hotspot {e[0]} recorded a {e[3]} displacement of {e[2]:+.0f} mm "
        f"in the {e[1]} epoch"
        for e in top
    ]
    return (". ".join(parts) + ". "
            "These episodic jumps suggest the presence of discrete failure or "
            "settlement events rather than uniform creep, warranting close monitoring.")


def _overall_verdict(risk_counts: Dict[str, int], hotspot_data: List[Dict]) -> str:
    n_critical = risk_counts.get("CRITICAL", 0)
    n_high     = risk_counts.get("HIGH", 0)
    n_medium   = risk_counts.get("MEDIUM", 0)
    n_total    = sum(risk_counts.values())

    worst = max(hotspot_data, key=lambda h: abs(h["cumulative_vertical_mm"]))

    if n_critical > 0:
        return (
            f"The monitored site is exhibiting critical ground deformation at "
            f"{n_critical} hotspot(s), with hotspot {worst['label']} recording "
            f"a cumulative vertical displacement of {worst['cumulative_vertical_mm']:.0f} mm. "
            f"This level of movement poses a direct risk to mine infrastructure and personnel safety. "
            f"Immediate engineering review and potential operational restrictions are strongly advised."
        )
    if n_high >= 2 or (n_high == 1 and n_medium >= 2):
        return (
            f"Significant ongoing deformation is detected across {n_high + n_medium} of "
            f"{n_total} monitored hotspots. Hotspot {worst['label']} shows the highest "
            f"cumulative vertical displacement at {worst['cumulative_vertical_mm']:.0f} mm. "
            f"The site is in an active deformation state and requires increased monitoring frequency "
            f"and geotechnical review before expanding mining operations."
        )
    if n_high == 1 or n_medium >= 2:
        return (
            f"Moderate deformation is present at several monitoring points, with the most "
            f"affected location ({worst['label']}) showing {worst['cumulative_vertical_mm']:.0f} mm "
            f"of cumulative vertical displacement. While not immediately critical, the pattern "
            f"indicates ongoing settlement that should be tracked with continued InSAR monitoring "
            f"and periodic ground-truth surveys."
        )
    return (
        f"The monitored area shows generally low-to-moderate ground deformation over the "
        f"observation period. Maximum cumulative vertical displacement is "
        f"{worst['cumulative_vertical_mm']:.0f} mm at hotspot {worst['label']}. "
        f"The site appears relatively stable under current conditions, though routine "
        f"satellite monitoring should continue to detect any emerging trends."
    )


def _recommended_actions(risk_counts: Dict[str, int], hotspot_findings: List[Dict]) -> List[str]:
    actions = []
    n_critical = risk_counts.get("CRITICAL", 0)
    n_high     = risk_counts.get("HIGH", 0)

    if n_critical > 0:
        actions.append(
            "Immediately notify the mine geotechnical engineer and conduct an emergency "
            "field inspection at all CRITICAL-rated hotspot locations."
        )
        actions.append(
            "Install or verify functioning of real-time ground movement sensors "
            "(prism targets or tiltmeters) at critical zones to complement satellite data."
        )
    if n_critical > 0 or n_high > 0:
        actions.append(
            "Reduce the InSAR monitoring interval to every 6-day Sentinel-1 revisit cycle "
            "to capture any acceleration in displacement rate."
        )
        actions.append(
            "Perform 2D slope stability analysis incorporating the measured subsidence and "
            "lateral displacement vectors to evaluate factor of safety."
        )
    else:
        actions.append(
            "Maintain current Sentinel-1 InSAR monitoring cadence (12–24 day interval) "
            "and archive results for long-term trend analysis."
        )

    actions.append(
        "Correlate observed displacement events with mine production records "
        "(blasting schedules, extraction volumes) to establish causation."
    )
    actions.append(
        "Re-run the full InSAR analysis pipeline after the next Sentinel-1 acquisition "
        "cycle to update displacement time series and recalculate risk levels."
    )
    return actions


# ── Core generator ────────────────────────────────────────────────────────────

def _generate_summary() -> Dict[str, Any]:
    cumulative, single_orbit = _parse_csv()
    hotspots   = _read_hotspots()
    site_cfg   = _read_site_config()

    lat  = site_cfg.get("lat", "unknown")
    lon  = site_cfg.get("lon", "unknown")
    t0   = site_cfg.get("start_date", "?")
    t1   = site_cfg.get("end_date",   "?")

    # Build per-hotspot findings
    hotspot_findings: List[Dict] = []
    risk_counts: Dict[str, int] = {}

    all_labels = sorted(set(list(cumulative.keys()) + list(single_orbit.keys())))

    for label in all_labels:
        if label in cumulative:
            vert = round(cumulative[label]["vertical_mm"], 1)
            ew   = round(cumulative[label]["ew_mm"], 1)
            epochs = cumulative[label].get("epochs", [])
            source = "2D decomposition"
        else:
            # Fallback: sum single-orbit vertical_approx
            rows = single_orbit[label]
            vert = round(sum(r["vert"] for r in rows), 1)
            ew   = 0.0
            epochs = []
            source = "single-orbit approx."

        risk = _risk_level(vert, ew)
        risk_counts[risk] = risk_counts.get(risk, 0) + 1

        hotspot_findings.append({
            "label": label,
            "risk_level": risk,
            "cumulative_vertical_mm": vert,
            "cumulative_ew_mm": ew,
            "key_finding": _hotspot_sentence(label, vert, ew, risk, epochs),
        })

    # Sort by risk severity then by magnitude
    _order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    hotspot_findings.sort(key=lambda h: (_order[h["risk_level"]], -abs(h["cumulative_vertical_mm"])))

    # Derive worst hotspot for executive summary
    if hotspot_findings:
        worst = max(hotspot_findings, key=lambda h: abs(h["cumulative_vertical_mm"]))
        n_affected = sum(1 for h in hotspot_findings if h["risk_level"] in ("HIGH", "CRITICAL"))
        exec_summary = (
            f"Sentinel-1 InSAR analysis of the mine site at coordinates "
            f"({lat}, {lon}) over {t0}–{t1} reveals active ground deformation "
            f"across all {len(hotspot_findings)} monitored hotspots. "
            f"Hotspot {worst['label']} is the most severely affected, with a cumulative "
            f"vertical displacement of {worst['cumulative_vertical_mm']:.0f} mm "
            f"and a lateral shift of {worst['cumulative_ew_mm']:.0f} mm. "
            f"{n_affected} hotspot(s) are classified as HIGH or CRITICAL risk, "
            f"indicating that the site requires active geotechnical management."
        )
    else:
        exec_summary = "No displacement data could be parsed from the results CSV."

    return {
        "executive_summary": exec_summary,
        "observation_period": (
            f"Monitoring period: {t0} to {t1} using Sentinel-1 SAR (C-band, "
            f"ascending and descending passes). Displacement resolved via 2D "
            f"ASC+DSC vector decomposition where both orbits were available."
        ),
        "hotspot_analysis":   hotspot_findings,
        "critical_events":    _detect_critical_events(cumulative, single_orbit),
        "overall_verdict":    _overall_verdict(risk_counts, hotspot_findings),
        "recommended_actions": _recommended_actions(risk_counts, hotspot_findings),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/generate")
def generate_summary() -> Dict[str, Any]:
    """Return cached summary if available, otherwise generate and cache it."""
    if SUMMARY_CACHE.exists():
        with open(SUMMARY_CACHE, "r", encoding="utf-8") as f:
            cached = json.load(f)
        cached["cached"] = True
        return cached

    if not REPORT_CSV.exists():
        raise HTTPException(
            status_code=404,
            detail="No results CSV found. Run the analysis pipeline first (page 7)."
        )

    try:
        summary_data = _generate_summary()
    except Exception as e:
        logger.error(f"Summary generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(e)}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SUMMARY_CACHE, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    summary_data["cached"] = False
    return summary_data


@router.delete("/cache")
def clear_summary_cache() -> Dict[str, str]:
    """Delete the cached summary so the next GET /generate regenerates it."""
    if SUMMARY_CACHE.exists():
        SUMMARY_CACHE.unlink()
        return {"message": "Cache cleared. Next request will regenerate the summary."}
    return {"message": "No cache to clear."}
