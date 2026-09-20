"""Demo 4 —— 自然语言 -> 函数调用：用 Choice 选函数，用 Choice/Score 填参数

场景：LLM 的 function calling 是生成式的 —— 它「写」出一段 JSON，你得解析、
校验、处理幻觉参数。Jev 的做法相反：答案空间由你定义，模型只能从你给的
选项里挑，所以**结构上不可能**返回一个不存在的函数名或非法枚举值。

代价：Jev 不能生成自由文本参数（比如一段搜索关键词）。
所以实战里常见的分工是 —— Jev 定路由和枚举参数，自由文本参数再交给小模型或正则。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from jev_lite import load_env  # noqa: E402

load_env()
from typesafe_sdk import Choice, Noul, TypeSafeClient  # noqa: E402

client = TypeSafeClient()

# 你的「工具箱」。描述写清楚边界（what / not_for），模型的判断会稳很多。
TOOLS = {
    "set_temperature": {"what": "Change the thermostat target temperature",
                        "not_for": "Turning lights or music on and off"},
    "set_lights":      {"what": "Turn lights on/off or change brightness or color"},
    "play_music":      {"what": "Start, stop, or change music playback"},
    "lock_doors":      {"what": "Lock or unlock doors", "not_for": "Checking whether a door is locked"},
    "query_status":    {"what": "Read the current state of a device without changing it"},
    "none":            {"what": "No tool applies to this request"},
}

UTTERANCES = [
    "it's freezing in here",
    "make the living room a bit warmer and dim the lights",
    "is the front door locked?",
    "lock up, I'm going to bed",
    "play something upbeat",
    "what's the capital of France",
]


def route(utterance: str):
    r = client.system_one(
        state={"utterance": utterance},
        questions={
            "tool": Choice(instructions="Which tool should handle this request?", criteria=TOOLS),
            # 枚举参数：和工具一起投机性地问出来，用到哪个由代码决定
            "direction": Choice(
                instructions="If this changes a numeric setting, which direction?",
                criteria={"increase": "Up / warmer / brighter / louder",
                          "decrease": "Down / cooler / dimmer / quieter",
                          "absolute": "A specific target value is named",
                          "n_a": "Not a numeric change"},
            ),
            "room": Choice(
                instructions="Which room is mentioned?",
                criteria={"living_room": None, "bedroom": None, "kitchen": None, "unspecified": None},
            ),
            "is_read_only": Noul(instructions="The request only asks for information and changes nothing."),
            "multi_step": Noul(instructions="The request asks for two or more distinct actions."),
        },
    )
    return r.answers, r.usage


if __name__ == "__main__":
    for u in UTTERANCES:
        a, usage = route(u)
        tool, conf = a["tool"].choice, a["tool"].confidence
        # 低置信度 -> 反问，而不是猜。这是 Jev 相对生成式 function calling 最大的优势。
        if conf < 0.7:
            print(f'"{u}"\n   -> 置信度不足 ({conf})，反问用户而不是猜。第二候选: '
                  f'{sorted(a["tool"].probabilities.items(), key=lambda kv: -kv[1])[:2]}')
            continue
        args = []
        if a["direction"].choice != "n_a":
            args.append(f"direction={a['direction'].choice}")
        if a["room"].choice != "unspecified":
            args.append(f"room={a['room'].choice}")
        note = "  [read-only]" if a["is_read_only"].noul > 0.7 else ""
        note += "  [多步请求, 需要拆分]" if a["multi_step"].noul > 0.7 else ""
        print(f'"{u}"\n   -> {tool}({", ".join(args)})  conf={conf}{note}')
