# 06 · API & SDK 速查

## HTTP API —— 整个产品只有一个端点

```
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

### 请求

```jsonc
{
  "model": "jev-latest",              // 必填
  "state": "..." | {...} | [...],     // 必填：文本 / JSON 对象 / 文本数组
  "questions": {                       // 必填：id -> question
    "<id>": {
      "type": "noul" | "choice" | "score",
      "instructions": "..." | {...} | [...],   // 可以是 JSON 结构
      "criteria": ...                          // noul 可选；choice/score 必填
    }
  }
}
```

| type | criteria | 约束 |
|---|---|---|
| `noul` | 可选，`{"true": ..., "false": ...}` | — |
| `choice` | **必填**，`{key: 描述}` | ≤ 255 项（256 → 400），描述可为 `null` |
| `score` | **必填**，`[档位描述, ...]` | 有序，上限 10 档（11 → 400）；下限文档说 2，实测未强制 |

### 响应

```jsonc
{
  "model": "jev-1.13.0",
  "answers": {
    "<id>": {"type": "noul",   "noul": 0.98},
    "<id>": {"type": "choice", "choice": "billing", "confidence": 1.0,
             "probabilities": {"billing": 1.0, "technical": 0.0}},
    "<id>": {"type": "score",  "score": 1.45, "confidence": 0.48,
             "legend": {"0": "can wait", "1": "this week"},
             "probabilities": {"0": 0.04, "1": 0.5}}
  },
  "usage": {"input_tokens": 394, "output_tokens": 69}
}
```

**只有 `input_tokens` 计费**（$42 / 十亿 = $0.042 / 百万）。output 免费。

### 模型

```bash
curl -H "Authorization: Bearer $KEY" https://api.typesafe.ai/v1/models
# Python SDK: client.models.list()
```

| 别名 | 解析到 | 说明 |
|---|---|---|
| `jev-latest` | `jev-1.13.0` | 稳定版，SDK 默认 |
| `jev-preview` | `jev-1.13.0` | 预览版，目前与 latest 相同 |

实测两者在同一个模糊样本上输出几乎一致（mixed, conf 0.92 vs 0.91）。

---

## Python SDK

```bash
uv pip install typesafe-sdk     # 需要 Python >= 3.10
```

> 如果本机有 SOCKS 代理（`ALL_PROXY=socks5://...`），
> SDK 底层的 httpx 会报 `ImportError: Using SOCKS proxy, but the 'socksio' package is not installed`。
> 补一个 `uv pip install socksio` 就好。

```python
from typesafe_sdk import TypeSafeClient, AsyncTypeSafeClient, Choice, Score, Noul

client = TypeSafeClient()                      # 自动读 TYPESAFE_API_KEY
client = TypeSafeClient(model="jev-preview")   # 覆盖默认模型

r = client.system_one(
    state="I was charged twice. Please help ASAP.",
    questions={
        "billing": Noul(instructions="Is this about billing?"),
        "tone":    Choice(instructions="What is the tone?",
                          criteria={"calm": None, "angry": None}),
        "urgency": Score(instructions="How urgent is this?",
                         criteria=["low", "medium", "high"]),
    },
)
r.answers["billing"].noul          # 0.98
r.answers["tone"].choice           # "angry"
r.answers["tone"].confidence       # 1.0
r.answers["urgency"].score         # 2.0
r.usage.input_tokens               # 计费口径
```

异步：

```python
async with AsyncTypeSafeClient() as client:
    r = await client.system_one(state=..., questions=...)
```

重试与超时：

```python
from typesafe_sdk import RetryPolicy
client = TypeSafeClient(retry=RetryPolicy(max_retries=3, backoff_max=0.2, timeout=1.0))
```

错误处理：

```python
from typesafe_sdk import TypeSafeAPIError
try:
    client.system_one(state, questions)
except TypeSafeAPIError as e:
    print(e.status, e.request_id)
```

完整异常族（都继承 `TypeSafeError`）：
`TypeSafeAuthenticationError` / `TypeSafeBadRequestError` / `TypeSafeRateLimitError` /
`TypeSafeUnprocessableEntityError` / `TypeSafePermissionDeniedError` /
`TypeSafeNotFoundError` / `TypeSafeInternalServerError` /
`TypeSafeAPIConnectionError` / `TypeSafeAPITimeoutError` / `TypeSafeAPIResponseValidationError`

环境变量：

| 变量 | 默认 |
|---|---|
| `TYPESAFE_API_KEY` | 必填 |
| `TYPESAFE_BASE_URL` | `https://api.typesafe.ai` |
| `TYPESAFE_DEFAULT_MODEL` | `jev-latest` |
| `TYPESAFE_LOG_LEVEL` | — |

---

## JavaScript / TypeScript SDK

```bash
npm install @typesafe-ai/sdk       # 需要 Node >= 20
```

```ts
import { choice, TypeSafeClient } from "@typesafe-ai/sdk";

const client = new TypeSafeClient();
const response = await client.systemOne({
  state: { document: "I was charged twice. Please fix this ASAP." },
  questions: {
    category: choice("What is this ticket about?", {
      billing: null, technical: null, other: null,
    }),
  },
});
console.log(response.answers.category.choice);
```

**答案类型由问题推导** —— `answers.category` 是 `ChoiceAnswer`，
写 `.score` 会直接编译报错。这是 TS 版本比 Python 版本爽的地方。
包同时提供 ESM / CommonJS / 类型声明。

---

## Agent Skill（给 Claude Code 之类的 agent 用）

```bash
claude plugin marketplace add typesafe-ai/skills
claude plugin install typesafe@typesafe-ai
# 其他 agent
npx skills add typesafe-ai/skills --skill typesafe-ai
```

SKILL.md 原文：`https://raw.githubusercontent.com/typesafe-ai/skills/main/skills/typesafe-ai/SKILL.md`

---

## 控制台

| 页面 | 用途 |
|---|---|
| `/playground` | 左边写 state + questions，右边看结果；有 Noul/Choice/Score 三个交互教程 |
| `/keys` | 创建/撤销 key。**key 是组织级的**，创建者被移除后仍然有效；明文只显示一次 |
| `/usage` | 按 key 的用量（有延迟） |

---

## 其他接入方式

| 入口 | 地址 |
|---|---|
| OpenRouter | `https://openrouter.ai/~typesafe/jev-latest` |
| Vercel AI Gateway | `https://vercel.com/ai-gateway/models/jev` |
| 官网 Waitlist（送 $5） | `https://typesafe.ai` → Join Waitlist |
