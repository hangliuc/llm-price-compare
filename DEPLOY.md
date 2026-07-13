# 部署指南

## 架构概览

```
本地/GitHub  ──push──>  GitHub 仓库 (master)
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
      GitHub Pages   CI Tests   Deploy-to-Server
      (静态前端)    (pytest)    (SSH + Docker)
                                   │
                                   ▼
                          服务器 129.226.94.179
                          Docker 容器 (cron 抓取)
                                   │
                          每日 11:00 抓取 → git push
                                   │
                                   ▼
                          GitHub Pages 自动更新
```

---

## 一、本地验证（不用推到服务器）

### 1. 运行测试

```bash
cd llm-price-compare
pip install -r requirements.txt
pytest scripts/ -v -m "not browser"
```

### 2. 验证前端

```bash
cd llm-price-compare
python3 -m http.server 8000
```

浏览器打开 `http://localhost:8000/ui/`，可看到前端页面。
数据来自 `data/prices.json`，修改后刷新即可看效果。

### 3. 手动跑抓取脚本

```bash
cd llm-price-compare
python3 scripts/run_daily.py
cat data/prices.json | python3 -m json.tool | head -30
cat data/run_status.json
```

注意：真实厂商抓取可能因页面改版失败，属正常现象。manual 厂商数据一定会加载。

### 4. Docker 本地验证

```bash
cd llm-price-compare
cp .env.example .env
# 编辑 .env 填入配置

# 构建并启动
docker compose up -d --build

# 手动触发一次抓取
docker compose run scraper run

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

---

## 二、服务器部署（Docker）

### 1. 首次部署

在服务器上：

```bash
ssh user@129.226.94.179

# 克隆仓库
cd /root
git clone git@github.com:hangliuc/llm-price-compare.git
cd llm-price-compare

# 配置环境变量
cp .env.example .env
vi .env
```

`.env` 内容：

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/openapis/bot/v2/hook/xxx
GIT_REMOTE_URL=https://<token>@github.com/hangliuc/llm-price-compare.git
GIT_USER_NAME=llm-price-bot
GIT_USER_EMAIL=bot@llm-price-compare
```

> **GIT_REMOTE_URL** 中的 `<token>` 是 GitHub Personal Access Token：
> GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token，勾选 `repo` 权限。

### 2. 启动容器

```bash
cd /root/llm-price-compare
docker compose up -d --build
```

容器会：
- 每日 11:00 北京时间自动执行 `scripts/run_daily.py`
- 抓取后将 `prices.json` git push 回 GitHub
- 失败时发飞书告警

### 3. 手动触发抓取

```bash
docker compose run scraper run
```

### 4. 查看日志

```bash
# 容器日志
docker compose logs -f

# cron 日志
docker exec llm-price-scraper cat /var/log/llm-price/cron.log
```

### 5. 后续更新

master 分支 push 后，GitHub Actions 会自动 SSH 到服务器执行：
```bash
git pull origin master
docker compose down
docker compose up -d --build
```

无需手动登录服务器。

---

## 三、SSH 密钥配置（GitHub Actions 自动部署）

### 1. 生成密钥对

在本地执行：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/llm-price-deploy -C "github-actions-deploy" -N ""
```

生成两个文件：
- `~/.ssh/llm-price-deploy` — 私钥（给 GitHub）
- `~/.ssh/llm-price-deploy.pub` — 公钥（给服务器）

### 2. 服务器安装公钥

```bash
ssh user@129.226.94.179

# 追加公钥到 authorized_keys
echo "ssh-ed25519 AAAA...（粘贴公钥内容）" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

或用一条命令完成（在本地执行）：

```bash
ssh-copy-id -i ~/.ssh/llm-price-deploy.pub user@129.226.94.179
```

### 3. GitHub 配置 Secrets

打开 `https://github.com/hangliuc/llm-price-compare/settings/secrets/actions`，添加 3 个 Secret：

| Secret 名称 | 值 |
|---|---|
| `SERVER_HOST` | `129.226.94.179` |
| `SERVER_USER` | 你的服务器用户名（如 `root` 或 `ubuntu`） |
| `SERVER_SSH_KEY` | 私钥全文（`cat ~/.ssh/llm-price-deploy` 的输出） |

### 4. 验证

push 到 master 后，在 GitHub Actions 页面查看 `Deploy to Server` workflow 是否成功。

---

## 四、GitHub Pages 配置

1. 打开仓库 `Settings → Pages`
2. Source 选择 `GitHub Actions`
3. master 分有 `data/prices.json` 或 `ui/` 变更时，`deploy.yml` 自动部署
4. 访问地址：`https://hangliuc.github.io/llm-price-compare/`

---

## 五、故障排查

| 问题 | 排查方式 |
|---|---|
| 抓取失败 | `docker compose logs` 或 `docker exec llm-price-scraper cat /var/log/llm-price/cron.log` |
| 数据未更新 | 检查 `data/run_status.json` 的 `last_push_at` 和 `consecutive_failures` |
| git push 失败 | 检查 `.env` 中 `GIT_REMOTE_URL` 的 token 是否有效 |
| 飞书告警未收到 | 检查 `.env` 中 `FEISHU_WEBHOOK_URL` |
| 自动部署失败 | GitHub Actions 页面查看 `Deploy to Server` 日志 |
| SSH 连接失败 | 检查 `SERVER_SSH_KEY` 私钥格式、`SERVER_HOST`、`SERVER_USER` |
