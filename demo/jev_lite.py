"""零依赖 Jev 客户端 —— 用来看清 HTTP 层到底发生了什么。

生产环境请用官方 SDK (`pip install typesafe-sdk`)，它带重试、超时、类型推导。
这个文件的价值是：整个 TypeSafe API 就只有一个端点、一个 POST。
"""
from __future__ import annotations

import json
import os
import urllib.request

BASE_URL = os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai")
ENDPOINT = f"{BASE_URL}/v1/systemone"


def load_env(path: str = ".env") -> None:
    """把 .env 读进 os.environ（避免额外依赖 python-dotenv）。"""
    if not os.path.exists(path):
        return
    for line in open(path):
        key, _, value = line.strip().partition("=")
        if key and not key.startswith("#"):
            os.environ.setdefault(key, value)


def noul(instructions, criteria=None) -> dict:
    q = {"type": "noul", "instructions": instructions}
    if criteria is not None:
        q["criteria"] = criteria
    return q


def choice(instructions, criteria: dict) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def score(instructions, criteria: list) -> dict:
    return {"type": "score", "instructions": instructions, "criteria": criteria}


def system_one(state, questions: dict, model: str = "jev-latest") -> dict:
    """POST /v1/systemone —— 这就是全部的 API 表面。"""
    api_key = os.environ["TYPESAFE_API_KEY"]
    body = json.dumps({"model": model, "state": state, "questions": questions}).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


if __name__ == "__main__":
    load_env()
    result = system_one(
        state="My card was charged twice for invoice INV-9921.",
        questions={
            "billing": noul("The message is about a billing problem."),
            "team": choice(
                "Which team should handle this?",
                {"billing": "Payments and invoices", "technical": "Bugs", "sales": "Pricing"},
            ),
            "urgency": score("How urgent?", ["can wait", "this week", "today", "right now"]),
        },
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
