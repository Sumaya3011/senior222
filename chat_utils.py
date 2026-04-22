import json
import os

from openai import OpenAI

# reads OPENAI_API_KEY from environment
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def ask_chatbot(messages: list[dict]) -> str:
    """
    messages: list of {"role": "system"|"user"|"assistant", "content": "..."}
    returns assistant text.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",     # or any chat model you prefer
            messages=messages,
            temperature=0.5,
            max_tokens=800,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception:
        # Keep /chat successful even if the LLM backend is unavailable.
        return json.dumps(
            {
                "explanation": (
                    "I am having trouble reaching the AI service right now. "
                    "Please try again in a moment."
                ),
                "summary": "AI service temporarily unavailable.",
            }
        )
