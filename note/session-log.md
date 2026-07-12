# 会话记录

## 2026-07-12: 项目从 0 到 MVP

### 关键决策

1. **架构选型**: 方案 A — 单仓静态站 + 定时抓取
   - Python 适配器跑在自建服务器 → prices.json → git push → GitHub Pages 自动重建
   - 不用 GitHub Actions cron（延迟大），用服务器 cron

2. **厂商范围**: 6 家适配器（OpenAI/Anthropic/智谱/火山引擎/DeepSeek/OpenCode）+ 4 家 manual（Google/Mistral/阿里通义/月之暗面）

3. **波动阈值**: >20% 警告，>50% 阻断（用户要求更严格）

4. **失败可见性**: 双通道 — 网页 stale 标记 + 飞书 webhook 告警

5. **前端**: Vue 3 CDN 引入，无 build step

6. **部署方式**: Docker（本日新增决策，替代原始 venv + cron 方案）

### 执行过程

- brainstorming skill 完成设计 → writing-plans skill 生成 24 task 计划
- Subagent 驱动模式：每个 task 派发独立 subagent，TDD 流程
- 24 个 task 全部完成，41 个测试通过
- 6 个适配器 fixture 测试验证了解析逻辑，真实抓取需后续调选择器

### 文件位置

- 设计文档: [design.md](./design.md)
- 实现计划: [plan.md](./plan.md)

---

## 2026-07-12: Docker 化 + GitHub 推送 + 自动部署

### 用户需求

1. 项目使用 Docker 部署
2. 推送到 GitHub (hangliuc/llm-price-compare)
3. master 更新时自动推送到服务器 (129.226.94.179)
4. 创建 note/ 目录记录设计和决策
5. commit 要简单清晰
6. 本地验证方式

### 关键决策

1. **Docker 方案**: Dockerfile (python:3.11-slim + cron + playwright) + docker-compose.yml
   - 容器内 cron 每日 11:00 北京时间执行 run_daily.py
   - `docker compose run scraper run` 可手动触发一次抓取

2. **自动部署**: GitHub Actions deploy-to-server.yml
   - master push 触发 → SSH 到服务器 → git pull + docker compose up --build
   - 使用 appleboy/ssh-action

3. **SSH 密钥**: ed25519，公钥放服务器 authorized_keys，私钥放 GitHub Secrets

4. **Git push 权限**: 容器内用 Personal Access Token 配置 GIT_REMOTE_URL

5. **分支名**: master（非 main）

### 产出文件

- `Dockerfile` / `entrypoint.sh` / `docker-compose.yml` / `.dockerignore` / `.env.example`
- `.github/workflows/deploy-to-server.yml`
- `note/` 目录（design.md + plan.md + session-log.md）
- `DEPLOY.md` 全面更新
