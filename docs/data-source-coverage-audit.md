# PPK 统一数据源覆盖率审计

> 审计日期：2026-08-20
>
> 目的：在确定 V3 数据架构前，验证是否存在一个接口可以覆盖 PPK 当前需要的按需计费、模型元数据和套餐数据。

## 1. 审计结论

**没有发现一个数据源能够完整替代 PPK 当前全部数据。**

最接近当前 UI 需求的是 Models.dev，但它仍然不能单独完成全部工作：

- 覆盖 PPK 当前 11 个按需计费 Provider 家族中的 10 个；
- 缺少火山引擎中国区的直接报价；
- 对应直接 Provider 目录约有 345 条模型服务记录，而 PPK 当前有 651 条按需记录；
- 不能替代 PPK 当前 49 条 Subscription / Coding Plan；
- Cache 价格不是所有模型都有；
- 当前 PPK 的部分记录本身包含渠道、地区、历史版本或别名重复，不能简单以 651 条作为必须保留的正确基线。

因此，当前最简单且可落地的方案不是“一个 API 包办全部”，而是：

```text
Models.dev
  负责大部分按需计费和模型元数据

+ 火山引擎本地补充

+ 官方套餐 Adapter 数据

= PPK Catalog
```

这仍然没有字段级仲裁：每条报价只由一个明确来源负责。

### 审核后的范围调整

产品侧已提出 V3 不再展示火山引擎。按这个新范围计算：

```text
V3 目标按需 Provider：10 个
Models.dev 覆盖：10 个
Provider 家族覆盖率：100%
```

这意味着 V3 第一阶段不再需要为了火山引擎保留独立 Adapter 或本地补充报价。本文后续涉及火山引擎的数字仍保留，用于记录为什么旧范围是 10/11；它不再属于建议的新 Catalog 范围。

## 2. 当前 PPK 数据基线

本次以当前 V2 发布文件为基线：

```text
runtime/v2/public/v2/catalog.json
```

当前数据规模：

| 数据 | 数量 |
|---|---:|
| Provider | 15 |
| 按需计费模型记录 | 651 |
| 套餐 | 49 |

其中，真正具有按需计费模型的 Provider 为 11 个：

| PPK Provider | 当前记录数 |
|---|---:|
| Anthropic | 55 |
| AWS | 186 |
| DeepSeek | 19 |
| Google | 66 |
| MiniMax | 16 |
| Kimi | 33 |
| OpenAI | 155 |
| 阿里通义 | 88 |
| 火山引擎 | 13 |
| 小米 | 4 |
| 智谱 | 16 |

Cursor、GitHub Copilot、Kiro、OpenCode 主要服务套餐和 Coding Tool 场景，不应按模型 API 报价覆盖率与上述 11 个 Provider 混算。

## 3. Models.dev 实测

### 3.1 数据源

官方说明：

- 项目：[anomalyco/models.dev](https://github.com/anomalyco/models.dev)
- API：`https://models.dev/api.json`
- 模型元数据：`https://models.dev/models.json`
- 合并 Catalog：`https://models.dev/catalog.json`

Models.dev 官方也明确说明，并不存在包含所有可用 AI 模型的单一数据库。其数据由社区维护，并按“模型由哪个服务 Provider 提供”组织。

本次下载的 API 数据包含：

| 指标 | 数量 |
|---|---:|
| Provider/渠道入口 | 192 |
| Model Offering | 6,840 |
| 同时具有 Input/Output 价格 | 6,415 |
| 具有 Context | 6,840 |
| 具有 Cache Read 价格 | 4,050 |

这里的 6,840 不是 6,840 个互不重复的基础模型，而是“某个模型由某个 Provider/渠道提供”的服务记录。同一个模型可能在多个渠道出现。

### 3.2 PPK 目标 Provider 映射

| PPK | Models.dev Provider | 是否覆盖 | Models.dev 记录数 | 备注 |
|---|---|---:|---:|---|
| Anthropic | `anthropic` | 是 | 13 | Anthropic 直接 API |
| AWS | `amazon-bedrock` | 是 | 120 | Amazon Bedrock |
| DeepSeek | `deepseek` | 是 | 4 | DeepSeek 直接 API |
| Google | `google` | 是 | 39 | Gemini Developer API；Vertex 另有独立入口 |
| MiniMax | `minimax-cn` | 是 | 7 | 中国区；国际区另有 `minimax` |
| Kimi | `moonshotai-cn` | 是 | 10 | 中国区；国际区另有 `moonshotai` |
| OpenAI | `openai` | 是 | 47 | OpenAI 直接 API |
| 阿里通义 | `alibaba-cn` | 是 | 86 | 中国区；国际区另有 `alibaba` |
| 火山引擎 | 无匹配入口 | **否** | 0 | 需要本地补充或独立 Adapter |
| 小米 | `xiaomi` | 是 | 6 | 另有 Token Plan 地区入口 |
| 智谱 | `zhipuai` | 是 | 13 | 另有 Z.AI 和 Coding Plan 入口 |

Provider 家族覆盖率：

```text
10 / 11 = 90.9%
```

### 3.3 映射后的字段覆盖

以上 10 个直接 Provider 入口合计：

| 字段 | 有值记录数 | 相对 345 条 |
|---|---:|---:|
| Model Offering | 345 | 100% |
| Input Price | 336 | 97.4% |
| Output Price | 336 | 97.4% |
| Context | 345 | 100% |
| Cache Read Price | 179 | 51.9% |

缺少 Cache 价格并不一定表示数据错误。很多模型或 Provider 本身没有公布 Cache 价格，UI 应显示 `—`，不能填 0。

### 3.4 不能直接替换 651 条的原因

PPK 当前记录数明显高于 Models.dev 对应直接 Provider 入口，主要可能来自：

- 历史模型版本；
- 日期别名；
- `latest` 浮动别名；
- AWS、Vertex 等渠道副本；
- 中国区和国际区；
- Standard、Batch、Flex 等服务层级；
- 聚合源产生的重复或近似身份。

因此不能把“Models.dev 只有 345 条”直接解释为丢失 306 个有效模型。正式迁移前需要把现有 651 条分成：

1. 当前有效的厂商直接报价；
2. 有意义的渠道报价；
3. 有意义的地区/服务层级；
4. 历史或下线模型；
5. 重复别名或错误合并。

## 4. Portkey 实测

### 4.1 数据源

- 项目：[Portkey-AI/models](https://github.com/Portkey-AI/models)
- Provider JSON：`https://configs.portkey.ai/pricing/{provider}.json`
- 单模型 API：`https://api.portkey.ai/model-configs/pricing/{provider}/{model}`

Portkey 是开源价格库，提供无鉴权价格 API。其价格单位是“美分 / Token”，接入时必须换算成“美元 / 1M Tokens”。

本次下载的仓库包含：

| 指标 | 数量 |
|---|---:|
| Pricing Provider 文件 | 46 |
| Pricing 记录 | 约 3,217 |

### 4.2 PPK 目标 Provider 覆盖

| PPK | Portkey Provider | 是否覆盖 | 价格记录数 |
|---|---|---:|---:|
| Anthropic | `anthropic` | 是 | 34 |
| AWS | `bedrock` | 是 | 187 |
| DeepSeek | `deepseek` | 是 | 5 |
| Google | `google` | 是 | 141 |
| MiniMax | `minimax` | 是 | 3 |
| Kimi | `moonshot` | 是 | 17 |
| OpenAI | `openai` | 是 | 189 |
| 阿里通义 | `dashscope` | 是 | 142 |
| 火山引擎 | 无中国区直接匹配 | 否 | 0 |
| 小米 | 无匹配 | 否 | 0 |
| 智谱 | `zhipu` | 是 | 18 |

Provider 家族覆盖率：

```text
9 / 11 = 81.8%
```

Portkey 还有 `byteplus`，但 BytePlus 国际渠道不能直接视为火山引擎中国区价格，因此本次没有把它算成火山引擎覆盖。

### 4.3 优缺点

优点：

- 价格历史版本多；
- 定价字段丰富；
- Batch 与标准价格结构明确分开；
- API 免费且无需鉴权。

缺点：

- 缺少小米和火山引擎；
- 价格单位是美分/Token，错误换算风险较高；
- Context、模态和模型能力不如 Models.dev 的结构直接；
- 记录多并不等于当前有效的厂商直接模型多，仍包含大量版本和服务入口。

## 5. 其他候选

### 5.1 LiteLLM

本次同时下载了 LiteLLM 最新公开价格库：

```text
https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json
```

文件共有 3,055 个顶层记录（包含一个 `sample_spec`）。按 PPK 目标 Provider 映射后的结果：

| PPK | LiteLLM Provider | 记录数 | Input/Output 均为正数 | Context | Cache 字段 | 判断 |
|---|---|---:|---:|---:|---:|---|
| Anthropic | `anthropic` | 26 | 26 | 26 | 26 | 可用 |
| AWS | `bedrock` | 268 | 187 | 261 | 38 | 可用，但包含多种模式和地区 |
| DeepSeek | `deepseek` | 12 | 12 | 12 | 9 | 可用 |
| Google | `gemini` | 78 | 54 | 69 | 37 | 可用，但并非每条都有 Token 价格 |
| MiniMax | `minimax` | 10 | 6 | 6 | 6 | 部分可用 |
| Kimi | `moonshot` | 22 | 22 | 22 | 12 | 可用 |
| OpenAI | `openai` | 222 | 138 | 141 | 105 | 可用，但混有图像、音频等模式 |
| 阿里通义 | `dashscope` | 43 | 25 | 41 | 8 | 部分可用 |
| 火山引擎 | `volcengine` | 12 | **0** | 12 | 0 | 不可作为真实价格源 |
| 小米 | 无 | 0 | 0 | 0 | 0 | 缺失 |
| 智谱 | `zai` | 13 | 11 | 13 | 6 | 部分可用，偏 Z.AI 国际入口 |

LiteLLM 虽然存在 12 条 `volcengine` 记录，但本次检查中没有一条同时具有大于 0 的 Input 和 Output 价格。把这些 0 直接发布会让 UI 错误显示为“免费”，因此不能算作有效价格覆盖。

结论：

- LiteLLM 能识别 10/11 个目标 Provider 名称；
- 真正具有可用正数 Token 价格的目标 Provider 为 9/11；
- 小米缺失；
- 火山引擎只有模型元数据，没有可用价格；
- 不覆盖 PPK 的 49 条套餐；
- 部分 Provider 同时包含文本、图像、音频、Embedding、地区和渠道记录，需要过滤和身份归一化。

因此 LiteLLM **不能全部覆盖 PPK 数据**。当前 PPK 看起来覆盖了 15 个 Provider，是因为 LiteLLM 之外还叠加了官网 Adapter 和本地 Manual，并不是 LiteLLM 单独完成的。

如果 V3 继续使用 LiteLLM，它应成为单一主源，不能再与 OpenRouter 和官网字段混合。但仍至少需要本地补充小米、火山引擎和全部套餐。从“减少特殊规则”的目标看，它不是本轮首选。

### 5.2 OpenRouter

OpenRouter API 只表达 OpenRouter 平台可路由的模型和价格。它适合独立的渠道价格目录，不适合作为所有厂商官网直销价格的替代品。

### 5.3 Artificial Analysis

[Artificial Analysis Data API](https://artificialanalysis.ai/data-api/docs) 提供模型价格和性能数据，但：

- 需要 API Key；
- 免费层主要是模型级聚合数据；
- Provider 级价格和服务信息需要 Commercial 权限；
- 不覆盖 Subscription / Coding Plan。

它更适合后期补充 Benchmark 和性能指标，不适合作为当前免费基础价格库。

### 5.4 Helicone

Helicone 有开源成本计算和模型注册包，但没有发现比 Models.dev 或 Portkey 更适合 PPK 的单一、公开、完整目录接口。它主要服务请求观测和成本计算，不作为本次主源候选。

## 6. 套餐覆盖结论

以下数据仍然需要 PPK 自己维护：

- ChatGPT Free / Plus / Pro / Business；
- Claude Free / Pro / Max；
- Gemini 订阅；
- Cursor Pro；
- GitHub Copilot 套餐；
- Kiro 套餐；
- Coding Plan；
- Developer/API Credit Plan。

Models.dev 中出现 `github-copilot`、`kimi-for-coding` 或各种 `coding-plan` Provider，并不表示它包含 PPK 当前所需的月费、购买权益和套餐产品。它们主要描述这些服务能够调用哪些模型及其服务成本。

因此当前 49 个 Plans 不应自动从 Models.dev 或 Portkey 生成。

### 6.1 Models.dev 中的 Coding Plan / Token Plan 到底是什么

Models.dev 的确包含以下 Provider 入口：

- `alibaba-coding-plan` / `alibaba-coding-plan-cn`；
- `alibaba-token-plan` / `alibaba-token-plan-cn`；
- `minimax-coding-plan` / `minimax-cn-coding-plan`；
- `xiaomi-token-plan-cn` / `xiaomi-token-plan-sgp` / `xiaomi-token-plan-ams`；
- `zai-coding-plan` / `zhipuai-coding-plan`；
- `kimi-for-coding`；
- `github-copilot`；
- 其他 Coding/Token Plan Endpoint。

但这些对象描述的是：

```text
这个 Coding Plan / Token Plan Endpoint
可以调用哪些模型
以及模型的能力、Context 和 Endpoint 内成本表达
```

它们不是：

```text
用户可以购买的套餐档位和价格表
```

Models.dev Provider Schema 只有 Provider 名称、API 地址、文档地址和模型列表；Model Schema 主要包含模型能力、Context 和按 1M Tokens 计算的 `cost`。当前 Schema 没有 PPK 套餐页面需要的：

- `monthly_price`；
- `first_month_price`；
- `billing_cycle`；
- 套餐档位名称；
- 套餐额度；
- Quota Unit；
- 主要权益；
- Purchase URL；
- Free/Paid 商业状态。

### 6.2 为什么大量 Cost 是 0

本次检查 Coding/Token Plan Provider 后发现，大多数模型的 `cost.input` 和 `cost.output` 都是 0。例如：

| Models.dev Provider | 模型数 | Input/Output 均为 0 |
|---|---:|---:|
| Alibaba Token Plan | 25 | 25 |
| Alibaba Token Plan China | 25 | 25 |
| MiniMax Token Plan 国际 | 7 | 7 |
| MiniMax Token Plan 中国 | 7 | 7 |
| Xiaomi Token Plan 中国 | 7 | 7 |
| Xiaomi Token Plan 新加坡 | 7 | 7 |
| Xiaomi Token Plan 欧洲 | 7 | 7 |
| Kimi For Coding | 4 | 4 |
| Z.AI Coding Plan | 5 | 5 |

这里的 0 不能解释为“套餐免费”。更合理的解释是：用户已经通过套餐获得 Endpoint 使用权，Models.dev 没有在单次模型调用层再次表达 Token 费用。

因此 PPK 不能把这些 0 映射为：

```text
月费 = 0
```

也不能据此生成 Free Plan。

GitHub Copilot 是另一个例子：Models.dev 能列出 Copilot Endpoint 支持的模型和模型成本，但没有 Copilot Free、Pro、Pro+、Business、Enterprise 等套餐的月费和权益。

### 6.3 Models.dev 可以减少多少套餐采集工作

Models.dev 不能替代套餐商业数据，但可以减少“套餐支持模型”这部分维护。

推荐将套餐拆成两个职责互不冲突的数据来源：

```text
PPK 官方套餐 Adapter
  自动采集：套餐名、月费、币种、周期、额度、权益、购买地址

Models.dev
  自动提供：对应 Endpoint 支持的模型、Context、模态、模型能力
```

两部分通过可选的 `modelsdev_provider_id` 关联。下面只是统一记录结构示例，由 Adapter 自动生成，不是人工编辑文件：

```json
{
  "plan_id": "qwen/coding-plan-pro",
  "provider_id": "qwen",
  "product_name": "百炼 Coding Plan Pro",
  "monthly_price": 149,
  "currency": "CNY",
  "modelsdev_provider_id": "alibaba-coding-plan-cn"
}
```

这不是仲裁，因为两边负责不同字段：

- PPK 不从 Models.dev 推断月费和权益；
- Models.dev 不覆盖 PPK 的套餐商业信息；
- 如果没有 `modelsdev_provider_id`，套餐仍可正常展示，只是不自动显示支持模型。

### 6.4 当前 49 条套餐的可替代程度

| 套餐类别 | Models.dev 能否替代 | 可利用内容 |
|---|---|---|
| ChatGPT / Claude / Gemini 通用订阅 | 否 | 基础模型元数据可复用，但没有订阅档位 |
| Cursor / Kiro | 否 | 没有完整套餐商业数据 |
| GitHub Copilot | 否 | 可获得 Endpoint 模型列表，不能获得套餐档位价格 |
| 阿里 Coding/Token Plan | 部分 | 可获得支持模型，月费和额度仍需官方套餐 Adapter 采集 |
| MiniMax Token Plan | 部分 | 可获得支持模型，月费和额度仍需官方套餐 Adapter 采集 |
| 小米 Token Plan | 部分 | 可获得支持模型，月费和额度仍需官方套餐 Adapter 采集 |
| 智谱 Coding Plan | 部分 | 可获得支持模型，月费和额度仍需官方套餐 Adapter 采集 |
| Kimi Coding | 部分 | 可获得 Coding Endpoint 模型，会员档位仍需官方套餐 Adapter 采集 |

最终判断：49 条套餐的**商业记录仍需由 PPK 自己采集**；V3 使用各厂商官方 API/页面 Adapter 自动完成，不保留人工维护的 `plans.yaml`。Models.dev 可以作为其中少数 Coding/Token Plan 的模型能力补充源。

## 7. 推荐选择

### 推荐：Models.dev 主源 + 官方套餐 Adapter

审核决策：V3 将 Models.dev 设为唯一自动模型/按需价格来源，不配置 LiteLLM、OpenRouter 或“按需价格官网 Adapter”作为运行时备选。套餐官方 Adapter 属于独立的套餐数据链路，不是 Models.dev 备选。下面对其他按需来源的内容仅保留为调研记录，不代表 V3 会接入这些来源。Models.dev 失败时本次不发布，线上继续使用上一份完整成功 Catalog。

```text
Models.dev
  └─ 新范围内 10 个按需 Provider 的模型、价格、Context、模态

PPK 官方套餐 Adapter
  └─ 49 条 Subscription / Coding Plan
```

选择 Models.dev 而不是 Portkey 的主要原因不是模型数量，而是：

1. 覆盖 10/11 个目标按需 Provider，高于 Portkey 的 9/11；
2. 包含小米；
3. Context 和 Modalities 更符合当前筛选与 Compare UI；
4. 价格已经是 USD / 1M Tokens，转换更简单；
5. Provider-specific Offering 的数据模型适合区分渠道。

### 不推荐

不推荐重新使用：

```text
Models.dev + Portkey + LiteLLM + OpenRouter + 官网
```

共同决定一个字段。这样会重新回到 V2 的复杂仲裁问题。

Portkey 可以作为 Phase 0 的一次性差异检查工具，但不进入日常发布链路。

## 8. 尚需验证的事项

在确认实施 V3 前，还需要完成一次模型级审计：

1. 将当前 651 条记录按 Direct/Channel/Region/Tier 分类；
2. 识别重复 Alias 和历史模型；
3. 列出 Models.dev 缺失但仍应在线展示的有效报价；
4. 核对 Models.dev 中 10 个目标 Provider 的官网来源和最新价格；
5. 明确 AWS、Google Vertex 是否属于首页默认目录还是独立渠道；
6. 明确 Batch/Flex 是否作为独立 Offering 展示；
7. 核对火山引擎 13 条本地报价；
8. 确认 49 条套餐的核验日期和来源 URL。

完成这些检查后，才能确定最终 Catalog 数量。V3 不应把“保留 651 条”作为目标，而应把“保留所有语义明确且仍有效的报价”作为目标。

## 9. 最终判断

| 问题 | 结论 |
|---|---|
| Models.dev 能否覆盖 PPK 全部数据？ | 不能 |
| 能否覆盖大部分按需计费？ | 可以，Provider 家族覆盖 10/11 |
| 主要缺口是什么？ | 火山引擎中国区、套餐、部分历史/渠道报价 |
| Portkey 是否覆盖更完整？ | 价格版本更多，但目标 Provider 只覆盖 9/11，且模型元数据较弱 |
| 是否存在能覆盖全部套餐的统一 API？ | 未发现 |
| 是否仍能取消仲裁？ | 可以；主源负责已覆盖记录，本地文件只负责明确缺口 |
| 当前最简单可行方案？ | 火山引擎暂不纳入范围；Models.dev + 官方套餐 Adapter |
