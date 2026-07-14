# 报名帖 · PPK · Price Per Token

> 用于 TRAE AI 创造力大赛报名提交。提交时把本文正文复制到社区发帖框，标题用下文标题，标签选「学习工作」。

---

**标签：** 学习工作

**标题：** 学习工作赛道 · PPK · 大模型选型从定价开始

---

## 正文

### 1. 创意名称 + 创意介绍

**创意名称：** PPK · Price Per Token — 主流大模型厂商定价聚合与选型平台

**想解决的问题：**
当前主流大模型 API 厂商超过 12 家，每家的计费方式、Token 单价、上下文窗口、订阅套餐都不一样，且经常调整。开发者在选型时需要打开十几个官网页面对比，信息极度分散且经常过期。在使用 AI Coding、跑 Agent 任务时，Token 消耗极快，选错模型可能让成本翻数倍。

**为什么想到做这个：**
自己在跑长任务 Agent 框架时，经常需要在 OpenAI / Anthropic / DeepSeek / 智谱 / 火山等几家之间切换，每次都要重新打开定价页核对——有的厂商还经常售罄（如智谱、火山的 Coding Plan）。市面上的价格对比工具要么只覆盖海外厂商，要么数据更新频率低，缺少一个真正面向国内开发者、覆盖订阅制和 Coding Plan 的实时聚合站。

**产品形态：**
一个静态网站 + 后端定时抓取系统。

### 2. 目标用户及痛点

**面向用户：**
- AI 应用开发者（独立开发者、创业团队）
- Agent / Workflow 框架使用者（OpenClaw、Coze、Dify 等用户）
- 企业技术选型负责人
- AI Coding 重度用户

**使用场景：**
- 项目启动前对比各厂商 Token 单价、上下文窗口，挑性价比最高的模型
- 抢购智谱 / 火山 / OpenCode 的 Coding Plan（经常售罄，需要快速比价）
- 评估订阅制（ChatGPT Plus、Claude Pro）vs 按 Token 计费哪个更划算

**用户痛点**
用户的痛点也是我前面说明为什么想到做这个。

**价值与意义**

### 3. 价值与意义

- 降低 AI 应用开发门槛，让个人开发者也能做出明智的成本决策
- 推动国产大模型厂商定价透明化，间接促进市场竞争

### 4. 创意产物 HTML

（此部分在社区发帖时，附上用 TRAE Work 生成的创意方案 HTML 文件，直接上传附件即可。）

建议在 TRAE Work 中用 Auto 模式，把上面三段内容贴进去，并补充提示词：

```
请基于以上创意介绍，生成一份完整的 HTML 创意方案展示页，包含：
1. 项目 Hero 区：标题「PPK · Price Per Token」+ slogan「选大模型，从定价开始」
2. 痛点展示区：12 家厂商定价页截图墙 + 「对比一次要打开 12 个标签页」
3. 解决方案区：三源交叉验证流程图 + 数据流架构图
4. 功能矩阵区：比价 / 筛选 / 厂商详情 / 价格波动告警 / Coding Plan 抢购
5. 数据覆盖区：12 家厂商 logo + 覆盖矩阵
6. 技术栈区：Vue 3 + Python + Docker + GitHub Actions
7. 路线图：MVP（已完成）→ 历史价格趋势 → 实时汇率 → 库存预警
```

把生成的 HTML 文件直接上传到报名帖附件即可。

---

## 提交前自查清单

- [ ] 标签选「学习工作」
- [ ] 标题格式：`学习工作赛道 · PPK · 大模型选型从定价开始`
- [ ] 正文 ≥ 100 字（当前约 800 字 ✅）
- [ ] 正文含 4 个必备部分 ✅
- [ ] 上传 TRAE Work 生成的 HTML 文件（待操作）
- [ ] TRAE 中国版与社区同一手机号
- [ ] 报名通过后去官网确认领取 https://www.trae.cn/ai-creativity/result

## 相关链接

- 报名指南：https://forum.trae.cn/t/topic/22548
- 报名专区：https://forum.trae.cn/c/38-category/39-category/39
- 保姆级教程：https://forum.trae.cn/t/topic/22569
- 赛事细则：https://bytedance.larkoffice.com/wiki/DScwwZPzsikvNzk5slJc2kgpnie
- 官网领奖入口：https://www.trae.cn/ai-creativity/result
- 项目线上：http://129.226.94.179:8001/ui/
- 项目仓库：https://github.com/hangliuc/llm-price-compare
