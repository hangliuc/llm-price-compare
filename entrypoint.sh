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
# 注意：git 初始化失败不应阻止 cron 启动（否则定时任务永远不执行）
if [ ! -d /app/.git ] && [ -n "$GIT_REMOTE_URL" ]; then
    echo "Initializing git repository from remote..."
    cd /app
    git init
    git remote add origin "$GIT_REMOTE_URL"
    git fetch origin master --depth=1 || echo "WARN: git fetch failed, continue without upstream"
    # 只移动 HEAD 指针，不覆盖工作区文件（Dockerfile 已 COPY 最新代码）
    git reset origin/master || echo "WARN: git reset failed, continue"
    # 设置 upstream tracking，让 git push 能直接工作
    # 容错：某些情况下分支名可能不是 master 或 origin/master 不存在
    git branch --set-upstream-to=origin/master master 2>/dev/null || \
        git config branch.master.remote origin 2>/dev/null || true
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
echo " Schedule: 0 5,11,17,23 * * * (每 6 小时)"
echo "============================================"
exec cron -f
