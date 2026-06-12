"""Local mock LLM used for offline lab execution."""

from __future__ import annotations

import random
import time


MOCK_RESPONSES = {
    "default": [
        "This is a mock AI response. In production this can be replaced by OpenAI or another LLM.",
        "The agent is running correctly and received your question.",
        "Your request was processed by the deployed AI agent.",
    ],
    "docker": [
        "Docker packages an application and its dependencies so it runs consistently across environments."
    ],
    "deploy": [
        "Deployment is the process of moving code from a local machine to a running service that users can access."
    ],
    "health": [
        "The agent is healthy and ready for platform health checks."
    ],
}


def ask(question: str, delay: float = 0.05) -> str:
    time.sleep(delay + random.uniform(0, 0.02))
    question_lower = question.lower()
    for keyword, responses in MOCK_RESPONSES.items():
        if keyword in question_lower:
            return random.choice(responses)
    return random.choice(MOCK_RESPONSES["default"])
