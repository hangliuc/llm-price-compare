FROM python:3.11-slim

ENV TZ=Asia/Shanghai
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    cron \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY . .

RUN mkdir -p /var/log/llm-price

# cron: 每 6 小时（05:00 / 11:00 / 17:00 / 23:00 北京时间）
RUN echo "0 5,11,17,23 * * * cd /app && /usr/local/bin/python3 scripts/run_daily.py >> /var/log/llm-price/cron.log 2>&1" \
    > /etc/cron.d/llm-price \
    && chmod 0644 /etc/cron.d/llm-price \
    && crontab /etc/cron.d/llm-price

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
