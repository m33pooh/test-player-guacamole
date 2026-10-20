import os
import random
from typing import Optional
import requests


class SocialResponder:
    """
    Social Responder for MapleStory chat interaction.
    Generates natural, casual, short gamer responses if other players chat.
    """

    CASUAL_RESPONSES = [
        "cc plz, just popped totem/frenzy",
        "map taken sry",
        "full here bro",
        "almost done my wap, 10 mins left",
        "just doing daily, leaving soon",
        "??",
        "yo, testing new rotation",
    ]

    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_base = api_base or os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", "nvidia/nemotron-3.5-lightning:free")

    def generate_chat_reply(self, message: str) -> str:
        """
        Generates a casual MapleStory gamer reply to an incoming message.
        """
        if not self.api_key:
            return random.choice(self.CASUAL_RESPONSES)

        prompt = (
            f"You are playing MapleStory. Another player just typed this message in chat:\n"
            f'"{message}"\n\n'
            f"Write a very short, casual, realistic MapleStory gamer response (1 sentence or under 8 words). "
            f"Do not use punctuation, stay polite but firm that you are farming this map. Output only the message text."
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 40,
            "temperature": 0.7,
        }

        try:
            url = f"{self.api_base.rstrip('/')}/chat/completions"
            resp = requests.post(url, headers=headers, json=payload, timeout=5.0)
            if resp.status_code == 200:
                reply = resp.json()["choices"][0]["message"]["content"].strip().strip('"')
                return reply
        except Exception:
            pass

        return random.choice(self.CASUAL_RESPONSES)
