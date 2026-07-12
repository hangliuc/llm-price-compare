# 部署指南

## 服务器端配置（cron 抓取）

### 1. 克隆仓库

```bash
cd /opt
git clone https://github.com/llm-price-compare/llm-price-compare.git
cd llm-price-compare
```

### 2. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 3. 配置环境变量

在 `~/.bashrc` 或 `/etc/llm-price.env` 中：

```bash
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/openapis/bot/v2/hook/xxx"
```

### 4. 配置 git push 权限

```bash
# 用 deploy key 或 personal access token
git remote set-url origin https://<token>@github.com/llm-price-compare/llm-price-compare.git
```

### 5. 配置 crontab

```bash
crontab -e
```

加入：

```
# 每日 11:00 北京时间抓取 LLM 价格
0 11 * * * cd /opt/llm-price-compare && /opt/llm-price-compare/.venv/bin/python3 scripts/run_daily.py >> /var/log/llm-price/$(date +\%Y\%m\%d).log 2>&1
```

### 6. 创建日志目录

```bash
sudo mkdir -p /var/log/llm-price
sudo chown $(whoami) /var/log/llm-price
```

### 7. 手动测试

```bash
cd /opt/llm-price-compare
source .venv/bin/activate
python3 scripts/run_daily.py
cat data/run_status.json
```

## GitHub Pages 配置

1. 仓库 Settings → Pages → Source: GitHub Actions
2. push 后 deploy.yml 自动部署
3. 访问 `https://llm-price-compare.github.io/llm-price-compare/`

## 故障排查

- **抓取失败**：检查 `/var/log/llm-price/` 日志
- **数据未更新**：检查 `git push` 是否成功（看 `data/run_status.json` 的 `last_push_at`）
- **飞书告警未收到**：检查 `FEISHU_WEBHOOK_URL` 环境变量
