"""Demo 3 —— 语义检索重排：把「哪一段真的回答了问题」变成一个可比较的数字

场景：RAG 里向量检索召回了 10 段候选。向量相似度只告诉你「话题相近」，
不告诉你「真的回答了问题」。用 Jev 对每段打一个 0-3 的分，代码按分数排序、
按阈值截断 —— 这一步在大模型生成之前，便宜到可以对每个 query 都做。

技巧：把 10 段候选放进**一次**调用的 10 个问题里，而不是循环调 10 次。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from jev_lite import load_env  # noqa: E402

load_env()
from typesafe_sdk import Score, TypeSafeClient  # noqa: E402

client = TypeSafeClient()

QUERY = "How do I rotate an API key without downtime?"

PASSAGES = [
    "API keys are organization-scoped and remain active even after the creator is removed.",
    "To rotate without downtime, create a second key, deploy it to all services, verify traffic "
    "on the new key, then revoke the old one. Both keys are valid at the same time.",
    "Our pricing is $42 per billion input tokens; output tokens are not billed.",
    "If a key is exposed, revoke it immediately from the console. Revocation takes effect in seconds.",
    "The dashboard shows usage per key so you can confirm the new key is receiving traffic before "
    "you revoke the old one.",
    "Rate limits are 250,000 tokens per second and 1,200 requests per minute.",
    "Set the TYPESAFE_API_KEY environment variable and the SDK picks it up automatically.",
    "Support is available on Discord for all users during the beta.",
]

RUBRIC = [
    "Irrelevant to the question",
    "Same topic, but does not answer the question",
    "Partially answers the question",
    "Directly and completely answers the question",
]


def rerank(query: str, passages: list[str], keep_above: float = 1.5):
    # 一次调用，N 个问题。state 里带上 query，让每个问题都能引用它。
    questions = {
        f"p{i}": Score(
            instructions={"task": "Rate how well this passage answers the user's question",
                          "question": query, "passage": p},
            criteria=RUBRIC,
        )
        for i, p in enumerate(passages)
    }
    r = client.system_one(state={"query": query}, questions=questions)
    ranked = sorted(
        ((r.answers[f"p{i}"].score, r.answers[f"p{i}"].confidence, p) for i, p in enumerate(passages)),
        reverse=True,
        key=lambda t: t[0],
    )
    kept = [t for t in ranked if t[0] >= keep_above]
    return ranked, kept, r.usage


if __name__ == "__main__":
    ranked, kept, usage = rerank(QUERY, PASSAGES)
    print(f"QUERY: {QUERY}\n")
    for s, conf, p in ranked:
        mark = "KEEP" if s >= 1.5 else "drop"
        print(f"  [{mark}] {s:4.2f} (conf {conf:4.2f})  {p[:76]}")
    print(f"\n{len(PASSAGES)} 段候选 -> 保留 {len(kept)} 段送进生成模型")
    print(f"1 次 API 调用, {usage.input_tokens} input tokens ≈ ${usage.input_tokens * 0.042 / 1e6:.8f}")
