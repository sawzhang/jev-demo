# Jev / TypeSafe 学习与实测

一次完整的 Jev 上手记录：概念 → API → 实测 → 5 个可运行 demo。
所有数字都是 2026-09-20 在 `jev-1.13.0` 上跑出来的，脚本可复现。

---

## 一句话：Jev 是什么

**Jev 不是聊天模型，是「判断模型」。** 你给它一份材料（state）和一组带类型的问题
（questions），它返回**带概率的结构化答案** —— 不生成一个字的自由文本。

```
LLM:  文本 in  ->  文本 out  ->  你写正则/JSON schema 去解析  ->  祈祷它别幻觉
Jev:  文本 in  ->  类型化答案 out（答案空间由你定义）  ->  直接 if/else
```

TypeSafe 把它叫 **System One 模型**（取自 Kahneman 的双系统理论）：
System 1 是快速直觉判断，System 2 是慢速推理。LLM 擅长 System 2，Jev 专做 System 1。

它**做不到**的事（官方明说）：写回复、写代码、解释自己的推理过程。
它换来的是：亚秒级延迟、百万分之一美元级成本、结构上不可能返回非法值。

---

## 30 秒跑通

```bash
# 1. 拿 key: https://console.typesafe.ai/keys -> Create key
echo 'TYPESAFE_API_KEY=apikey_xxx' > .env

# 2. 装 SDK（需要 Python >= 3.10）
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python typesafe-sdk

# 3. 跑
.venv/bin/python demo/jev_lite.py
```

最小 HTTP 调用 —— **整个 API 只有这一个端点**：

```bash
curl -X POST https://api.typesafe.ai/v1/systemone \
  -H "Authorization: Bearer $TYPESAFE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "jev-latest",
    "state": "My card was charged twice for invoice INV-9921.",
    "questions": {
      "billing": {"type": "noul", "instructions": "The message is about a billing problem."},
      "team":    {"type": "choice", "instructions": "Which team should handle this?",
                  "criteria": {"billing": "Payments", "technical": "Bugs", "sales": "Pricing"}},
      "urgency": {"type": "score", "instructions": "How urgent?",
                  "criteria": ["can wait", "this week", "today", "right now"]}
    }
  }'
```

返回：

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "billing": {"type": "noul", "noul": 0.98},
    "team":    {"type": "choice", "choice": "billing", "confidence": 1.0,
                "probabilities": {"billing": 1.0, "technical": 0.0, "sales": 0.0}},
    "urgency": {"type": "score", "score": 1.45, "confidence": 0.48,
                "legend": {"0": "can wait", "1": "this week", "2": "today", "3": "right now"},
                "probabilities": {"0": 0.04, "1": 0.5, "2": 0.43, "3": 0.03}}
  },
  "usage": {"input_tokens": 394, "output_tokens": 69}
}
```

注意 `urgency.confidence = 0.48` —— 模型在「这周」和「今天」之间摇摆，
它**如实告诉你它不确定**。这个信号是 Jev 最值钱的地方，见 [docs/03-confidence.md](docs/03-confidence.md)。

---

## 三个原语，全部

| 原语 | 问的问题 | criteria | 返回 |
|---|---|---|---|
| **Noul** | 「这句话是真的吗？」 | 可选，描述 true/false 边界 | `noul`: 0~1 概率 |
| **Choice** | 「是哪一个？」 | **必填**，选项 → 描述的 map（≤255 项） | `choice` + `probabilities` + `confidence` |
| **Score** | 「在哪一档？」 | **必填**，有序档位数组（2~10 档） | `score`（可落在档位之间）+ `legend` + `probabilities` + `confidence` |

三种可以在同一次调用里混用，对同一份 state 并行评估、互不影响。

详见 [docs/02-primitives.md](docs/02-primitives.md)。

---

## 实测结论（这部分是我自己跑出来的，不是抄文档）

### 1. 扇出几乎免费 —— 这是用好 Jev 的核心

| 问题数 | 耗时 | input tokens | 成本 |
|---:|---:|---:|---:|
| 1 | 0.53s | 305 | $0.0000128 |
| 4 | 0.49s | 346 | $0.0000145 |
| 12 | 0.53s | 449 | $0.0000189 |
| **40** | **0.52s** | 817 | $0.0000343 |

**40 个问题和 1 个问题耗时一样。** 所以正确姿势不是「先分类，再根据分类追问」，
而是**把所有可能用到的问题一次全问完**，让代码去挑哪些有意义。
`demo/01_triage.py` 就是这么做的：8 个问题一次问完，跑完整棵决策树，零额外往返。

### 2. 官方「已知弱点」实测：8 项里只有 1 项真的翻车

官方 [model-jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13) 列了 9 类失败模式。
我逐条压测（`demo/05_benchmark.py`）：

| 场景 | 期望 | 实测 | |
|---|---|---|---|
| 计数 17 项 | 17→高，16/18→低 | 0.99 / 0.01 / 0.01 | PASS |
| **日期窗口（让模型自己算天数）** | **≈0.0（实际 42 天 > 30 天）** | **0.26** | **FAIL** |
| 同题，代码先算好 `days=42` | ≈1.0 | 0.99 | PASS |
| 双重否定 | ≈1.0 | 0.93 | PASS |
| 噪声淹没信号（signal 夹在 120 句废话中间） | 分类不变 | auth(1.0)，与干净输入一致 | PASS |
| state 内提示注入 | ≈0.0 | 0.01 | PASS |
| P(x) + P(¬x) | 不保证 = 1 | 0.02 + 0.97 = 0.99 | PASS |
| 中文 | 能判对 | anger=2.93, 类别=物流 | PASS |

**唯一稳定复现的弱点是日期/时间计算。** 模型把日期当文本读，不当有序量。
规避方式很简单也很关键 —— **算数在代码里做，判断才交给模型**：

```python
# 差：让模型自己算日期差         -> 0.26（模糊，错的）
Noul("The return request is within the policy window.")

# 好：代码算好天数放进 state      -> 0.99（干净，对的）
state = {..., "days_elapsed": 42, "policy_days": 30}
Noul("`days_elapsed` exceeds `policy_days`.")

# 最好：这题根本不用问模型
days_elapsed > policy_days
```

抗提示注入和抗噪声的表现比文档写的乐观得多，但**不要当成安全保证** ——
官方明确说「不默认把数据当敌意输入」，生产环境仍需自己的防线。

### 3. Choice 的低置信度会如实反映「多意图」

`demo/04_function_calling.py` 里这句：

```
"make the living room a bit warmer and dim the lights"
  -> conf=0.38, probabilities: set_temperature 0.48 / set_lights 0.40
```

这是一个**双动作**请求，模型没有硬选一个，而是把概率劈成两半、置信度掉到 0.38。
代码据此反问用户，而不是猜。生成式 function calling 通常会自信地只调一个。

---

### 4. 这整份学习 + 实测的总成本

控制台 Usage 页显示：**60 次请求，38,931 tokens，合计 $0.0014**。

包含全部探索、5 个 demo 的多轮调试、压测脚本跑 3 遍、255 选项的极限测试。
一杯咖啡能买大约 2 万次这样的学习过程。

---

## Demo 一览

| 文件 | 演示什么 |
|---|---|
| [`demo/jev_lite.py`](demo/jev_lite.py) | 零依赖客户端（60 行），看清 HTTP 层只有一个 POST |
| [`demo/01_triage.py`](demo/01_triage.py) | **投机性扇出 + 置信度闸门**：8 问一次调用跑完整棵工单分诊决策树 |
| [`demo/02_guardrails.py`](demo/02_guardrails.py) | **LLM 护栏**：越狱/PII/越界/有害 5 道并行检查，成本比大模型低 3~4 个数量级 |
| [`demo/03_semantic_rerank.py`](demo/03_semantic_rerank.py) | **RAG 重排**：8 段候选一次打分排序，向量相似度之上再加一层「是否真的回答了问题」 |
| [`demo/04_function_calling.py`](demo/04_function_calling.py) | **NL → 函数调用**：答案空间封闭，结构上不可能幻觉出不存在的函数 |
| [`demo/05_benchmark.py`](demo/05_benchmark.py) | 可复现实测：扇出扩展性 + 9 类已知弱点逐条压测 + 错误边界 |

```bash
bash demo/run_all.sh          # 全部跑一遍
```

---

## 文档索引

- [01 · 核心概念](docs/01-concepts.md) —— System One vs LLM，state 怎么组织
- [02 · 三原语详解](docs/02-primitives.md) —— Noul / Choice / Score，含结构化 criteria 进阶用法
- [03 · 置信度](docs/03-confidence.md) —— 怎么算的、怎么当第二根决策轴用
- [04 · 四种架构模式](docs/04-patterns.md) —— 扇出 / 置信度路由 / 复合打分 / 意图路由
- [05 · 弱点与规避](docs/05-limitations.md) —— 9 类 jaggedness + 实测 + 规避写法
- [06 · API & SDK 速查](docs/06-api-sdk-reference.md) —— 端点、字段、限额、错误码、Python/JS SDK

## 官方资源

| | |
|---|---|
| 控制台 | https://console.typesafe.ai （Playground / API Keys / Usage） |
| 文档 | https://docs.typesafe.ai |
| 全文索引（喂给 agent 用） | https://docs.typesafe.ai/llms.txt |
| Agent Skill | `claude plugin marketplace add typesafe-ai/skills` → `claude plugin install typesafe@typesafe-ai` |
| 其他入口 | OpenRouter `~typesafe/jev-latest`、Vercel AI Gateway |
