import json

from chat_utils import ask_chatbot
from schemas.requests import ChatRequest
from services.map_service import resolve_city, clamp_map_date, parse_iso_date, display_date


def chat(req: ChatRequest):
    city_name, lat, lon = resolve_city(req.city)
    da = clamp_map_date(parse_iso_date(req.date_a))
    db = clamp_map_date(parse_iso_date(req.date_b))

    system_msg = {
        "role": "system",
        "content": (
            "You are TerraScope AI, a friendly and knowledgeable assistant for the TerraScope "
            "Earth Change Monitoring app. You help users understand satellite-based land cover maps, "
            "environmental changes, and how to use the app.\n\n"
            "IMPORTANT RULES:\n"
            "- Be conversational and natural. If the user says 'hi', 'hello', greet them warmly. "
            "If they say 'thank you' or 'thanks', reply kindly (e.g. 'You're welcome! Let me know if you need anything else.'). "
            "Do NOT respond to casual messages with technical map explanations.\n"
            "- Only discuss maps, land cover, and analysis when the user asks about them.\n"
            "- Keep answers concise and easy to understand. Avoid jargon unless the user is technical.\n"
            "- You can suggest what the user could try next (e.g. 'Try switching to Change mode to compare two dates').\n\n"
            "APP CONTEXT:\n"
            "- The app uses Google Earth Engine Dynamic World data (annual composites of land cover classes).\n"
            "- Modes: Home (single map view), Change (compare two dates), Time Series (video over years), "
            "Prediction (AI-predicted future land cover).\n"
            "- Land cover classes: Water, Trees, Grass, Flooded Vegetation, Crops, Shrub & Scrub, "
            "Built Area, Bare Ground, Snow & Ice.\n"
            f"- Current mode: {req.mode}, date A: {display_date(da)}, date B: {display_date(db)}.\n"
            f"- Current region: {city_name} at ({lat:.3f}, {lon:.3f}).\n\n"
            "Return your answer STRICTLY as JSON with two keys: "
            "'explanation' (your full reply, 1-3 sentences) and "
            "'summary' (1 short sentence for the map subtitle)."
        ),
    }

    messages_for_api = [system_msg]

    if req.history:
        for h in req.history[-10:]:
            role = h.get("role", "user")
            content = h.get("content", "")
            if role in ("user", "assistant") and content:
                messages_for_api.append({"role": role, "content": content})

    messages_for_api.append({"role": "user", "content": req.message})

    try:
        raw = ask_chatbot(messages_for_api)
    except Exception as e:
        print(f"Chat backend error: {e}")
        return {
            "reply": "Sorry, I’m having trouble reaching the AI service right now. Please try again in a moment.",
            "summary": "AI service temporarily unavailable.",
        }

    explanation = raw
    summary = raw

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            explanation = data.get("explanation", raw)
            summary = data.get("summary", explanation)
    except Exception:
        parts = explanation.split(".")
        summary = ".".join(parts[:2]).strip()
        if summary and not summary.endswith("."):
            summary += "."

    return {
        "reply": explanation,
        "summary": summary,
    }
