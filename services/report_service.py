import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.change_detection_service import _compute_landcover_metrics

OPENAI_API_KEY = (os.environ.get("OPENAI_API_KEY") or "").strip()

TRANSITION_INTERPRETATIONS: Dict[str, str] = {
    "Crops->Trees": "may indicate reforestation, land abandonment, or seasonal orchard canopy growth",
    "Trees->Crops": "suggests deforestation for agricultural expansion",
    "Trees->Built area": "suggests urban expansion into forested land",
    "Trees->Bare ground": "may indicate logging, wildfire aftermath, or land clearing",
    "Trees->Grass": "could indicate selective logging, windstorm damage, or natural thinning",
    "Crops->Built area": "suggests urbanization of agricultural land",
    "Crops->Bare ground": "may indicate harvest, drought stress, or soil degradation",
    "Crops->Grass": "could reflect fallow rotation or crop failure",
    "Crops->Water": "may indicate seasonal flooding or irrigation reservoir expansion",
    "Water->Bare ground": "may indicate drought, reservoir depletion, or water extraction",
    "Water->Grass": "could indicate wetland drying or seasonal water recession",
    "Water->Crops": "may suggest receding floodwaters revealing agricultural land",
    "Water->Built area": "could indicate land reclamation or coastal development",
    "Bare ground->Built area": "suggests new construction or infrastructure development",
    "Bare ground->Water": "may indicate flooding, reservoir filling, or seasonal inundation",
    "Bare ground->Crops": "suggests new agricultural cultivation or seasonal planting",
    "Bare ground->Trees": "could indicate natural vegetation recovery or reforestation",
    "Bare ground->Grass": "may indicate vegetation regrowth after disturbance",
    "Grass->Built area": "suggests urban or suburban sprawl into grasslands",
    "Grass->Bare ground": "may indicate overgrazing, drought, or land degradation",
    "Grass->Trees": "could indicate natural succession or afforestation",
    "Grass->Crops": "suggests conversion of grassland to agriculture",
    "Grass->Water": "may indicate flooding of low-lying grassland areas",
    "Built area->Bare ground": "could indicate demolition, conflict damage, or construction site clearance",
    "Built area->Water": "may indicate coastal erosion or severe flooding of built-up areas",
    "Shrub & scrub->Built area": "suggests development encroaching on scrubland",
    "Shrub & scrub->Bare ground": "may indicate desertification, fire, or land clearing",
    "Shrub & scrub->Trees": "could indicate natural vegetation succession",
    "Flooded vegetation->Water": "may indicate deepening flood levels submerging vegetation",
    "Flooded vegetation->Bare ground": "could indicate flood recession followed by vegetation die-off",
    "Trees->Flooded vegetation": "suggests rising water levels partially submerging forested areas",
    "Grass->Flooded vegetation": "may indicate onset of flooding in low-lying meadows",
    "Crops->Flooded vegetation": "suggests cropland inundation from flood events",
    "Snow & ice->Water": "may indicate glacial melt or snowmelt runoff",
    "Snow & ice->Bare ground": "suggests seasonal snow retreat or accelerated glacial recession",
    "Water->Snow & ice": "could indicate seasonal freeze-up of water bodies",
}


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val or default)
    except (TypeError, ValueError):
        return default


def _describe_transition(from_name: str, to_name: str) -> str:
    key = f"{from_name}->{to_name}"
    if key in TRANSITION_INTERPRETATIONS:
        return TRANSITION_INTERPRETATIONS[key]
    return f"indicates a shift in land cover classification from {from_name} to {to_name}"


def _risk_threshold_explanation(
    risk: str, change: float, water_loss: float, veg_loss: float, built_change: float,
) -> str:
    parts = [
        f"This analysis detected {change:.2f}% total land cover change, "
        f"{water_loss:.2f}% water loss, {veg_loss:.2f}% vegetation loss, "
        f"and {built_change:.2f}% built-area change."
    ]
    if risk == "HIGH":
        reasons = []
        if change > 20:
            reasons.append(f"total change ({change:.2f}%) exceeds the 20% threshold")
        if water_loss > 7:
            reasons.append(f"water loss ({water_loss:.2f}%) exceeds the 7% threshold")
        if not reasons:
            reasons.append("the combined severity score across all indicators is elevated")
        parts.append(
            f"The risk level is HIGH because {' and '.join(reasons)}. "
            "HIGH risk signals significant landscape transformation that warrants "
            "immediate investigation and cross-referencing with ground truth data."
        )
    elif risk == "MEDIUM":
        parts.append(
            f"The risk level is MEDIUM because total change ({change:.2f}%) falls between "
            "the 5% and 20% thresholds, and none of the critical override conditions are met "
            f"(change ≤ 20%, water loss ≤ 7%). "
            "MEDIUM risk indicates notable changes worth investigating — verify with "
            "high-resolution imagery and seasonal context."
        )
    else:
        parts.append(
            f"The risk level is LOW because total change ({change:.2f}%) is below 5%, "
            f"water loss ({water_loss:.2f}%) is well below the 7% threshold, and all "
            "individual indicator scores remain in the lowest band. "
            "LOW risk suggests minimal landscape disruption during this period, "
            "though localized changes may still exist within the study area."
        )
    return " ".join(parts)


def _build_dynamic_metric_cards(
    change_pct: float,
    changed_pixels: int,
    total_pixels: int,
    water_loss: float,
    veg_loss: float,
    built_change: float,
    transitions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []

    cards.append({
        "label": "Pixels Changed",
        "value": f"{change_pct:.2f}%",
        "detail": f"{changed_pixels:,} of {total_pixels:,} sampled pixels",
        "icon": "change",
    })

    has_flooded_veg = any(
        t.get("from_name") == "Flooded vegetation" or t.get("to_name") == "Flooded vegetation"
        for t in transitions
    )

    if water_loss > 0.1 and len(cards) < 4:
        cards.append({
            "label": "Water Loss",
            "value": f"{water_loss:.2f}%",
            "detail": "Net decrease in water surface area",
            "icon": "water",
        })

    if veg_loss > 0.1 and len(cards) < 4:
        cards.append({
            "label": "Vegetation Loss",
            "value": f"{veg_loss:.2f}%",
            "detail": "Net decrease in trees, grass, crops, shrub, and flooded vegetation",
            "icon": "vegetation",
        })

    if built_change > 0.1 and len(cards) < 4:
        cards.append({
            "label": "Built Area Change",
            "value": f"{built_change:.2f}%",
            "detail": "Absolute change in built-up area coverage",
            "icon": "built",
        })

    if has_flooded_veg and len(cards) < 4:
        flooded_pct = sum(
            _safe_float(t.get("percent_of_aoi"))
            for t in transitions
            if t.get("to_name") == "Flooded vegetation"
        )
        cards.append({
            "label": "Flooded Vegetation",
            "value": f"{flooded_pct:.2f}%",
            "detail": "Land area transitioning to flooded vegetation state",
            "icon": "flood",
        })

    return cards[:4]


def _fallback_narrative(
    region: str,
    start: str,
    end: str,
    change: float,
    risk: str,
    water_loss: float,
    veg_loss: float,
    built_change: float,
    transitions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    region_display = region or "the study area"

    trans_descriptions: List[str] = []
    for t in transitions[:5]:
        fn = t.get("from_name") or t.get("from", "")
        tn = t.get("to_name") or t.get("to", "")
        pct = t.get("percent_of_aoi") or t.get("percent", 0)
        if fn and tn:
            interp = _describe_transition(fn, tn)
            trans_descriptions.append(f"{fn} → {tn} ({pct}% of AOI) — this {interp}")

    executive_summary = (
        f"This land cover change detection analysis examines {region_display} "
        f"between {start} and {end} using Google Dynamic World V1 satellite data. "
        f"The analysis detected {change:.2f}% total land cover change across the study area. "
        f"Based on the computed indicators, the overall risk level is assessed as {risk}."
    )

    if trans_descriptions:
        what_changed = (
            f"During the period from {start} to {end}, {region_display} experienced "
            f"measurable land cover changes affecting {change:.2f}% of the analyzed area. "
            f"The principal transitions observed are: {'. '.join(trans_descriptions)}. "
            "These transitions reflect the dominant landscape dynamics captured by "
            "Sentinel-2 imagery at 100 m resolution during the analysis window."
        )
    else:
        what_changed = (
            f"During the period from {start} to {end}, {region_display} experienced "
            f"{change:.2f}% total land cover change. No dominant single transitions were "
            "isolated above the reporting threshold, suggesting either distributed minor "
            "changes or classification noise across the study area."
        )

    impact_parts = []
    if water_loss > 0.5:
        impact_parts.append(
            f"The {water_loss:.2f}% net water surface loss in {region_display} may indicate "
            "hydrological stress, reduced streamflow, or reservoir drawdown — potentially "
            "affecting aquatic ecosystems, water availability, and downstream communities."
        )
    if veg_loss > 0.5:
        impact_parts.append(
            f"Vegetation cover decreased by {veg_loss:.2f}%, which could reduce carbon "
            "sequestration capacity, increase soil erosion susceptibility, and degrade "
            "habitat quality for local wildlife."
        )
    if built_change > 1.0:
        impact_parts.append(
            f"Built-area change of {built_change:.2f}% suggests active urbanization or "
            "infrastructure development, which can contribute to habitat fragmentation, "
            "increased impervious surface runoff, and urban heat island effects."
        )
    any_flood = any(
        (t.get("to_name") or t.get("to", "")) == "Flooded vegetation"
        for t in transitions
    )
    if any_flood:
        impact_parts.append(
            "The appearance of flooded vegetation transitions suggests active inundation "
            "events, which may impact agricultural productivity, displace wildlife, "
            "and introduce waterborne disease risk to affected communities."
        )
    if not impact_parts:
        impact_parts.append(
            f"The changes detected in {region_display} during this period are relatively "
            "contained. Environmental impacts appear limited, though localized effects "
            "may still be present at sub-pixel scales not captured by 100 m analysis."
        )
    environmental_impact = " ".join(impact_parts)

    risk_meaning = _risk_threshold_explanation(risk, change, water_loss, veg_loss, built_change)

    recs: List[str] = []
    if transitions:
        t0 = transitions[0]
        fn = t0.get("from_name") or t0.get("from", "Unknown")
        tn = t0.get("to_name") or t0.get("to", "Unknown")
        pct = t0.get("percent_of_aoi") or t0.get("percent", 0)
        if "Crops" in fn and "Trees" in tn:
            recs.append(
                f"Verify whether the {fn} → {tn} transition ({pct}% of AOI) in {region_display} "
                "represents genuine reforestation or seasonal canopy cover by checking "
                "agricultural calendars and harvest timing for the region."
            )
        elif "Water" in fn:
            recs.append(
                f"Cross-reference the {fn} → {tn} transition ({pct}% of AOI) with "
                f"precipitation records and reservoir level data for {region_display} "
                f"during {start} to {end} to distinguish drought from seasonal variation."
            )
        elif "Built" in tn:
            recs.append(
                f"Compare the detected {fn} → {tn} transition ({pct}% of AOI) against "
                f"construction permits and development plans for {region_display} "
                "to validate whether this reflects planned urbanization."
            )
        else:
            recs.append(
                f"Investigate the dominant {fn} → {tn} transition ({pct}% of AOI) using "
                f"high-resolution imagery for {region_display} to determine whether this "
                "change is a real landscape shift or a classification artifact."
            )

    if water_loss > 0.5:
        recs.append(
            f"Given the {water_loss:.2f}% water loss detected, obtain precipitation and "
            f"evapotranspiration records for {region_display} between {start} and {end} "
            "to assess whether this reflects natural drought cycles or anthropogenic extraction."
        )
    if veg_loss > 0.5:
        recs.append(
            f"With {veg_loss:.2f}% vegetation loss, check FIRMS active fire data and "
            f"drought indices (SPI/SPEI) for {region_display} during this period to "
            "rule out wildfire or severe drought as contributing factors."
        )
    if built_change > 1.0:
        recs.append(
            f"The {built_change:.2f}% built-area change warrants comparison with "
            f"municipal construction permits and urban planning records for {region_display} "
            "to confirm whether detected changes align with authorized development."
        )

    recs.append(
        f"Re-run the analysis for {region_display} with a tighter date window "
        "(±15 days instead of ±30) to reduce cloud contamination and seasonal noise."
    )
    recs.append(
        f"Use the Time Series mode to visualize month-by-month land cover evolution in "
        f"{region_display} across {start[:4]}–{end[:4]} for a more complete temporal picture."
    )

    return {
        "executive_summary": executive_summary,
        "what_changed": what_changed,
        "environmental_impact": environmental_impact,
        "risk_meaning": risk_meaning,
        "recommendations": recs[:3],
    }


def _call_openai_narrative(
    region: str,
    start: str,
    end: str,
    change: float,
    risk: str,
    water_loss: float,
    veg_loss: float,
    built_change: float,
    transitions: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not OPENAI_API_KEY or "PASTE_YOUR" in OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    top_trans = []
    for t in transitions[:8]:
        fn = t.get("from_name") or t.get("from", "")
        tn = t.get("to_name") or t.get("to", "")
        pct = t.get("percent_of_aoi") or t.get("percent", 0)
        if fn and tn:
            top_trans.append({"from": fn, "to": tn, "percent_of_aoi": pct})

    data_block = json.dumps({
        "region": region,
        "date_range": {"start": start, "end": end},
        "change_percent": change,
        "risk_level": risk,
        "water_loss_percent": water_loss,
        "vegetation_loss_percent": veg_loss,
        "built_change_percent": built_change,
        "top_transitions": top_trans,
    }, indent=2)

    prompt = f"""You are an expert environmental scientist specializing in remote sensing and \
land cover change analysis. Write a professional land cover change detection report based on \
the following data from Google Dynamic World V1 (Sentinel-2) analysis.

IMPORTANT RULES:
- Do NOT recalculate any numbers. Use the EXACT values provided below.
- Explain WHY the risk is {risk} using these exact thresholds: HIGH if change_percent > 20% \
OR water_loss > 7%. MEDIUM if change_percent is between 5% and 20%. LOW if all indicators \
are below their thresholds. State the exact numbers from this run and compare to thresholds.
- Interpret each transition ecologically and relate it to the specific region ({region}) and \
the season implied by the date range ({start} to {end}).
- Generate 3 specific actionable recommendations based on the actual findings — not generic advice.
- Each recommendation must reference the region name, specific metrics, or specific transitions.

DATA:
{data_block}

Return ONLY valid JSON (no markdown fences, no extra text) with exactly these keys:
- "executive_summary": 3-4 sentence professional overview mentioning region, date range, \
total change percentage, and risk level.
- "what_changed": Detailed paragraph explaining the land cover changes with ecological or \
human-activity interpretation of each top transition.
- "environmental_impact": 3-4 sentences about what the detected changes mean for the \
environment of this specific region. Vary by change type — floods → hydrological impact, \
droughts → water stress, urban expansion → habitat loss and heat islands.
- "risk_meaning": Explain exactly why the risk is {risk} using the actual threshold values \
and this run's exact numbers.
- "recommendations": Array of exactly 3 specific, actionable recommendations based on the \
actual detected transitions and metrics."""

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=1200,
        )
        raw = r.choices[0].message.content or "{}"
        out = json.loads(raw)
        required = ("executive_summary", "what_changed", "environmental_impact",
                     "risk_meaning", "recommendations")
        for k in required:
            if k not in out:
                return None
        if not isinstance(out["recommendations"], list):
            return None
        out["recommendations"] = out["recommendations"][:3]
        return out
    except Exception:
        return None


def build_structured_report(payload: dict) -> Dict[str, Any]:
    stats = payload.get("change_stats") or {}
    region = payload.get("region") or stats.get("region_label") or "Study area"
    dr = payload.get("date_range") or {}
    start = dr.get("start", stats.get("before_date", ""))
    end = dr.get("end", stats.get("after_date", ""))

    change = _safe_float(stats.get("change_percent"), 0.0)
    cb = stats.get("class_distribution_before") or []
    ca = stats.get("class_distribution_after") or []
    m = _compute_landcover_metrics(cb, ca, change)

    water_loss = m["water_loss_percent"]
    veg_loss = m["vegetation_loss_percent"]
    built_change = m["built_change_percent"]
    risk = m["risk_level"]

    transitions = stats.get("top_transitions") or []
    total_pixels = int(_safe_float(stats.get("total_sampled_pixels"), 0))
    changed_pixels = int(_safe_float(stats.get("changed_pixels"), 0))
    pixel_scale = int(_safe_float(stats.get("pixel_scale_m"), 100))

    gpt_narrative = _call_openai_narrative(
        region, start, end, change, risk,
        water_loss, veg_loss, built_change, transitions,
    )
    gpt_used = gpt_narrative is not None

    if gpt_narrative:
        narrative = gpt_narrative
    else:
        narrative = _fallback_narrative(
            region, start, end, change, risk,
            water_loss, veg_loss, built_change, transitions,
        )

    dynamic_cards = _build_dynamic_metric_cards(
        change, changed_pixels, total_pixels,
        water_loss, veg_loss, built_change, transitions,
    )

    return {
        "report_metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_source": "Google Dynamic World V1 (GOOGLE/DYNAMICWORLD/V1)",
            "satellite": "Sentinel-2",
            "pixel_scale": f"{pixel_scale} m",
            "ai_generated": gpt_used,
        },
        "metrics": {
            "region": region,
            "date_range": {"start": start, "end": end},
            "change_percent": round(change, 2),
            "risk_level": risk,
            "water_loss_percent": water_loss,
            "vegetation_loss_percent": veg_loss,
            "built_change_percent": built_change,
            "total_sampled_pixels": total_pixels,
        },
        "dynamic_metric_cards": dynamic_cards,
        "narrative": narrative,
        "top_transitions": transitions,
        "gpt_used": gpt_used,
    }
