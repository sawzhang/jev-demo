# Decisions 与 Jev：调研比较和验证计划

调研日期：2026-10-07。比较 TypeSafe 原生 Jev 与 OpenAI Decisions，不包含第三方代理。官方事实、仓库实测和设计建议分别列出；本次未调用 Decisions，也未新增付费测试。

## 官方资料核对

| 维度 | OpenAI Decisions | TypeSafe Jev |
|---|---|---|
| 当前模型 | gpt-6-luna，公开测试阶段 | jev-1.13.0；latest/preview 当前指向该版本 |
| 原语 | predicate / choice / score | noul / choice / score |
| 输入 | 文本和内嵌图片 | 文本、JSON对象或文本数组；无图片、音频、视频 |
| 自由文本生成 | 判断接口不承担解释、任意对象生成 | 不生成自由文本 |
| 多问题 | 共享输入上的独立问题可一起提交；依赖前题答案时分请求 | 同state独立并行判断；这是厂商说明，非恒定延迟保证 |
| 基础输入单价 | $0.10 / 百万token | $0.042 / 百万token |
| 输出计费 | 免费；无缓存读写收费 | 免费 |
| 附加价格 | 区域处理和长上下文可能加价 | 具体服务方案另核实 |
| 请求预算 | 此次指南未建立精确token上限 | 总64K；state加最长问题不超过32K |
| 吞吐 | 按账户可用限额核实，未作同口径比较 | 当前文档80请求/秒、100K token/秒；动态调整 |

资料：[OpenAI指南](https://developers.openai.com/api/docs/guides/decisions)、[Jev介绍](https://docs.typesafe.ai/introduction)、[Jev模型](https://docs.typesafe.ai/models)。这些是日期快照，不是未来价格或账户访问保证。

两者用途高度重叠。Decisions的图片输入是明确差异；Jev基础单价更低。没有同条件测试支持准确性或速度排名。不能从接口定位推断内部网络结构相同，或断言某一家复制另一家。

## 接口与迁移

| 字段 | Decisions | Jev |
|---|---|---|
| POST | /v1/decisions | /v1/systemone |
| 证据 | input | state |
| questions | 数组，name标识 | ID→question字典 |
| instructions | 字符串 | 字符串、对象或数组 |
| choice定义 | choices数组：value、description | criteria字典：键、描述 |
| choice值 | 字符串或布尔值，类型有区别 | 字符串 |
| score定义 | levels数组：label、description | 有序criteria数组 |
| answers / probabilities | 数组 | 字典 |
| 是非答案 | probability | noul |
| 单题拒绝 | refusal | 当前答案schema未列出对应类型；不代表永不拒绝 |

来源：[Decisions接口](https://developers.openai.com/api/reference/resources/decisions/methods/create)、[TypeSafe接口](https://docs.typesafe.ai/api)。Decisions不接受原生工具调用/输出消息，应将执行记录转成文本；图片须使用base64 data URL。

建议适配层保留问题名称、类型、原始分布、模型、用量、rubric版本及 scored/refusal/error 状态。拒绝、缺失、非法值和网络错误不能变成默认PASS。Jev结构化instructions转换成字符串时，保留原条件和边界；迁移后重新校准阈值。

## 判断语义与confidence

两者score均是有序等级索引的概率加权平均。平均分相同可能对应完全不同的分布：三档0/1/2中，(0,1,0)与(0.5,0,0.5)的score都为1；后者对极端状态不确定，需要补查。

Jev公开Choice公式：(p_max - 1/n) / (1 - 1/n)。六选项p_max=0.48得到约0.376，而不是三选项公式的0.22。Score使用另一种考虑等级距离的分布统计；Noul没有单独confidence。见[官方公式](https://docs.typesafe.ai/confidence)。

此次读取的Decisions指南和接口未给出confidence精确公式。不能假定两家同分可互换。confidence不是经验正确率；校准需要独立标注集。题目名只是标识，完整判断条件应写在instructions中。

## 成本比较的边界

相同计费输入token数量下，Decisions单价约为Jev的2.38倍，Jev低约58%。1亿输入token的基础费用分别为$10和$4.20。不同tokenizer、问题编码、图片、附加定价使相同材料未必具有相同费用。

应记录实际usage和账单，比较判断、补查、重试、复核及错误处置总成本。不能把筛选后的文件字节减少当作总token减少。现有Codex A/B中，全部文件25669 input token；筛选后20347加Jev筛选14466合计34813，本次没有证明总token节省。

## 已有实测与证据限制

见[运维实验报告](07-agent-evidence-learning.md)与results中的两轮原始JSON。10个合成案例、每轮40个Noul判断；v1/v2与预设标签分歧14/0，延迟中位数0.530/0.690秒。v2在同一组数据上调整题目，没有独立留出集；不能推导生产准确率100%或概率已经校准。尚无Decisions同条件实测。

OpenAI的约10倍速度说法以Responses API为基准，不是与Jev比较。本地端到端耗时含网络等因素，不能与纯推理宣传数字比较。单次1/4/12/40问题扇出样本也不能证明恒定延迟。

Jev[已知弱点](https://docs.typesafe.ai/model-jaggedness/jev-1.13)包括字面理解、数学和日期、多跳推理、无关长上下文、对抗内容、选项顺序。Decisions没有在所读页面提供同样的清单，不等于没有这些弱点。数字、日期、端口、主机与退出状态应由代码或实际检查确认。

## 数据边界与选择

Decisions指南说明符合条件客户可用ZDR/HIPAA及美国、欧洲相关区域控制；这些不是所有账户的默认配置。TypeSafe[法律说明](https://docs.typesafe.ai/legal)承诺不使用用户数据训练，并向企业提供ZDR；此次未建立同等地域控制能力。

设计建议：短文本筛选先保留现有Jev；图片场景评估Decisions；中文运维核验用双后端留出集比较。保留确定性后置检查，task_completed与response_integrity独立记录；如实报告失败可以通过诚信检查，但任务仍未完成。经验正文交给生成模型，并核对原始证据。

## 下一轮公平实验（未执行）

1. 冻结相同原始证据、评分标准和人工标签，分开调试集、校准集与留出集。
2. 留出集至少数百条，包含诚实失败、虚假成功、日志缺失、超时后成功、自动重启、错机器、首页200但业务失败、中文改写及提示注入。
3. 不将标签发送给模型。随机交错请求，固定网络环境，记录重复运行、超时、重试及拒绝。
4. 分别校准阈值，在相同虚假成功误放率下比较自动处理覆盖率；同时记录误报、灰区比例、Brier分数。
5. 测P50/P95端到端延迟、错误率、实际token与总成本；1/4/12/40题分别重复测试。
6. 对选项顺序和标签名称作扰动检查；对模型升级重新回归，记录实际返回版本。

当前结论：单价和图片能力已有文档依据；中文质量、延迟胜负和端到端成本排名尚待验证。
