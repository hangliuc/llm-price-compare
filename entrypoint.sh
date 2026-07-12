#!/bin/bash
set -e

# 配置 git
if [ -n "$GIT_USER_NAME" ]; then
    git config --global user.name "$GIT_USER_NAME"
fi
if [ -n "$GIT_USER_EMAIL" ]; then
    git config --global user.email "$GIT_USER_EMAIL"
fi

# 如果传入参数是 run，手动执行一次抓取
if [ "$1" = "run" ]; then
    cd /app
    exec python3 scripts/run_daily.py
fi

# 默认启动 cron 守护
echo "============================================"
echo " LLM Price Compare - Cron Service"
echo " TZ: Asia/Shanghai"
echo " Schedule: 0 11 * * * (每日 11:00)"
echo "============================================"
exec cron -f
