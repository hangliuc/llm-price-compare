#!/bin/bash
set -e

# 配置 git
if [ -n "$GIT_USER_NAME" ]; then
    git config --global user.name "$GIT_USER_NAME"
fi
if [ -n "$GIT_USER_EMAIL" ]; then
    git config --global user.email "$GIT_USER_EMAIL"
fi

# 容器首次启动时初始化 .git（.dockerignore 排除了 .git，需手动拉取）
# run_daily.py 的 git_commit_push 依赖 .git 目录
if [ ! -d /app/.git ] && [ -n "$GIT_REMOTE_URL" ]; then
    echo "Initializing git repository from remote..."
    cd /app
    git init
    git remote add origin "$GIT_REMOTE_URL"
    git fetch origin master --depth=1
    # 只移动 HEAD 指针，不覆盖工作区文件（Dockerfile 已 COPY 最新代码）
    git reset origin/master
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
