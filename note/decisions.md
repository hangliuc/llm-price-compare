# 关键决策记录 (Decisions)

> 记录设计与技术决策的「为什么」，与 commit message（「改了什么」）互补。
> 每次关键 commit 同步追加一条记录，最新在上。

## 记录模板

```
### YYYY-MM-DD · 决策标题
- **commit**: `<hash>` `<type>(<scope>): <subject>`
- **背景**: 遇到什么问题/动机
- **决策**: 做了什么取舍
- **被否决方案**: 考虑过但没采用的方案及原因
- **影响**: 涉及的文件/模块或后续约束
```

---

## 2026-07-16 · 字体系统统一为三层角色分工

- **commit**: `refactor(ui): 统一字体系统为三层角色分工`
- **背景**: 网站字体混乱，40 处 font-family 声明缺乏清晰角色分工。核心问题不是字体种类多，而是没有规则：
  - italic 滥用：衬线斜体同时扮演「品牌签名/关键词强调/序号装饰/英文 label」4 种角色
  - mono 滥用：等宽字体同时扮演「英文标签/数字/模型名/箭头符号」4 种角色
  - weight 不统一：同样 13px 文字出现 400/500/600 三种
  - letter-spacing 随意：11 种值（-0.04em ~ 0.08em）无规律
- **决策**: 建立三层角色分工系统
  - **Instrument Serif（展示层）**：仅用于页面大标题、关键数字、序号装饰。weight 统一 400。italic 仅用于关键词强调（hero-title em / section-title em / about-page h2 em），禁止用于序号、label、品牌副标题
  - **Geist（界面层）**：所有 UI 文字、正文、标签、按钮、卡片标题。weight 递进规则：400 正文 / 500 次级 / 600 强调标签 / 700 品牌。letter-spacing 按字号功能分 5 档：uppercase 标签 0.06em / ≥30px 衬线 -0.02em / 20-29px -0.015em / 14-19px -0.01em / ≤13px 正文 0
  - **Geist Mono（数据层）**：仅限数据与代码——价格、Token 数、模型 ID、上下文长度。必备 `font-variant-numeric: tabular-nums`。收窄到 3 种角色（num / card-prices / plan-item-price / card-model / card-ctx / plan-item-quota / currency-toggle）
  - 4 个衬线大标题加 `text-wrap: balance` 防孤行（Vercel Web Interface Guidelines 建议）
- **被否决方案**:
  - 引入新字体（如 Inter/Söhne 替换 Geist）：当前 3 字体已够，问题在角色分工不清而非字体选择本身
  - 全部统一为单一字体族：会丢失「编辑式科技产品」的衬线/无衬线对比特色，与项目定位冲突
  - 改用 CHANGELOG.md 记录变动：CHANGELOG 偏「发布了什么」适合有版本号项目，本项目是 cron 每日持续部署，无版本号语义；且易与 commit message 重复
- **影响**: `ui/style.css`（11 处字体声明修改）、`ui/index.html`（缓存 v17→v18）。后续新增 UI 模块需遵循三层角色规则；新增 commit 需同步追加本文件记录
