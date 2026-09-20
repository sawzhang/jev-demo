"""Demo 1 —— 工单分诊：一次调用跑完整棵决策树（Speculative Fan-out + Confidence Routing）

核心思想：
  传统 LLM 做法是「分类 -> 看结果 -> 再追问细节」，串行多轮。
  Jev 里所有问题并行评估，所以把**可能用到的问题一次全问**（包括投机性的），
  然后由代码决定哪些答案有意义。实测 40 个问题和 1 个问题耗时基本相同。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from jev_lite import load_env  # noqa: E402

load_env()
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient  # noqa: E402

client = TypeSafeClient()

TICKETS = [
    "Hi, the CSV export button on the reports page throws a 500. Steps: open /reports, "
    "pick last 30 days, click Export. Happens every time in Chrome and Safari. "
    "This blocks our Monday board meeting.",
    "I was charged $49 twice this month on invoice INV-2231. Nobody has replied in a week. "
    "Refund me or I'm calling my bank.",
    "Would be great if you supported dark mode one day. No rush at all.",
    "hi",
]

# 一次问 8 个问题。其中 bug_severity / has_repro 只有在 category=bug 时才有用，
# refund_requested 只有在 category=billing 时才有用 —— 这就是「投机性扇出」。
QUESTIONS = {
    "category": Choice(
        instructions="What kind of support ticket is this?",
        criteria={
            "bug_report": "Something in the product is broken or errors out",
            "billing": "Charges, invoices, refunds, subscriptions",
            "feature_request": "Asking for something that does not exist yet",
            "question": "Asking how to do something that already works",
            "unclear": "Not enough information to tell",
        },
    ),
    "bug_severity": Score(
        instructions="If this is a bug, how severe is it?",
        criteria=[
            "Cosmetic, no impact on work",
            "Annoying, there is a workaround",
            "Blocks a real workflow",
            "Data loss or total outage",
        ],
    ),
    "has_repro": Noul(instructions="The message contains concrete steps to reproduce the problem."),
    "refund_requested": Noul(instructions="The customer is asking for money back."),
    "frustration": Score(
        instructions="How frustrated does the customer sound?",
        criteria=["Calm", "Mildly annoyed", "Clearly angry", "Threatening to escalate or leave"],
    ),
    "deadline": Noul(instructions="The customer mentions a deadline or time pressure."),
    "legal_threat": Noul(instructions="The customer threatens legal action, a chargeback, or a bank dispute."),
    "actionable": Noul(instructions="There is enough information here to start working on this ticket."),
}


def triage(ticket: str) -> dict:
    """把 Jev 的答案交给普通 Python 控制流 —— 决策逻辑始终在你的代码里。"""
    r = client.system_one(state=ticket, questions=QUESTIONS)
    a = r.answers
    cat = a["category"]

    plan = {"route": None, "priority": "normal", "flags": [], "usage": r.usage}

    # 第一道闸门：置信度不够就不自动处理。
    # 答案告诉你「是什么」，置信度告诉你「敢不敢自动动手」—— 这是两个独立的轴。
    if cat.confidence < 0.60:
        plan["route"] = "human_triage"
        plan["flags"].append(f"low_confidence({cat.confidence})")
        return plan, a

    # 第二道闸门：分类很确定，但信息不足以开工。这不是模型不确定，是工单本身太空。
    if cat.choice == "unclear" or a["actionable"].noul < 0.5:
        plan["route"] = "ask_for_details"
        plan["flags"].append(f"not_actionable({a['actionable'].noul})")
        return plan, a

    if cat.choice == "bug_report":
        if a["bug_severity"].score >= 2.0 and a["has_repro"].noul > 0.6:
            plan["route"] = "engineering_escalation"
            plan["priority"] = "high"
        else:
            plan["route"] = "bug_backlog"
    elif cat.choice == "billing":
        plan["route"] = "billing_team"
        if a["refund_requested"].noul > 0.7:
            plan["flags"].append("refund_likely")
    elif cat.choice == "feature_request":
        plan["route"] = "product_backlog"
        plan["priority"] = "low"
    else:
        plan["route"] = "support_agent"

    # 横切规则：和分类无关，任何工单都适用
    if a["frustration"].score >= 2.0:
        plan["priority"] = "high"
        plan["flags"].append("angry_customer")
    if a["legal_threat"].noul > 0.6:
        plan["priority"] = "urgent"
        plan["flags"].append("LEGAL_THREAT")
    if a["deadline"].noul > 0.7:
        plan["flags"].append("has_deadline")

    return plan, a


if __name__ == "__main__":
    total_in = 0
    for ticket in TICKETS:
        plan, a = triage(ticket)
        total_in += plan["usage"].input_tokens
        print("=" * 78)
        print("TICKET:", ticket[:88] + ("..." if len(ticket) > 88 else ""))
        print(f"  category   : {a['category'].choice:16s} conf={a['category'].confidence}")
        print(f"  severity   : {a['bug_severity'].score:<5}  frustration: {a['frustration'].score}")
        print(f"  repro={a['has_repro'].noul}  refund={a['refund_requested'].noul}  "
              f"legal={a['legal_threat'].noul}  deadline={a['deadline'].noul}")
        print(f"  --> route={plan['route']}  priority={plan['priority']}  flags={plan['flags']}")
    print("=" * 78)
    print(f"{len(TICKETS)} 个工单 x 8 个问题 = {len(TICKETS)} 次 API 调用, "
          f"共 {total_in} input tokens ≈ ${total_in * 0.042 / 1e6:.8f}")
