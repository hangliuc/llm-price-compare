-- PPK SQLite Schema
-- 建表语句集中管理，后续新增表在此文件追加
-- 所有表用 IF NOT EXISTS，支持幂等执行

-- ========== 1. 每日价格快照 ==========
-- 记录每次抓取最终采用的数据，支持历史追溯
-- 单表设计：per_token/subscription/coding_plan 共用一张表，用 billing_type 区分
-- 拒绝分表理由：同一厂商常跨多种计费方式，分表后"列某厂商全部产品"需 UNION；
--               价格变动检测需跨计费方式统一 diff；raw_prices_json 已兜底未结构化字段
CREATE TABLE IF NOT EXISTS price_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,          -- 自增主键
  snapshot_date TEXT NOT NULL,                   -- 抓取日期 YYYY-MM-DD（北京时间），用于按日切片
  provider_id TEXT NOT NULL,                     -- 厂商 ID，如 openai/anthropic/qwen
  product_id TEXT NOT NULL,                      -- 产品 ID，如 gpt-5-token/chatgpt-plus/claude-pro
  billing_type TEXT NOT NULL,                    -- 计费类型：per_token（按 Token 计费）/ subscription（订阅制）/ coding_plan（编程额度套餐）
  model TEXT,                                    -- 模型名，如 GPT-5、Claude Sonnet 5、Qwen3.7-Max；subscription/coding_plan 可为空
  context_window INTEGER,                        -- 上下文窗口大小（Token 数），如 128000；subscription/coding_plan 通常为 null
  modalities TEXT,                               -- 支持的模态，JSON 数组，如 ["text","vision","file"]
  release_date TEXT,                             -- 模型发布日期 YYYY-MM-DD（来自 OpenRouter 元数据）
  -- ↓ per_token 专用字段（subscription/coding_plan 产品这些字段为 NULL）
  input_price REAL,                              -- 输入价格，每百万 Token 单价
  output_price REAL,                             -- 输出价格，每百万 Token 单价（通常为输入的 3-5 倍）
  cached_input_price REAL,                       -- 缓存命中价格（Prompt Caching），通常为 input_price 的 10%
  price_unit TEXT,                               -- 价格单位，如 per_1m_tokens（每百万 Token）
  -- ↓ subscription / coding_plan 专用字段（per_token 产品这些字段为 NULL）
  monthly_price REAL,                            -- 月费，如 ChatGPT Plus=20、Cursor Pro=20
  included_quota REAL,                           -- 包含额度数值，如 500（次）或 12000（calls）
  quota_unit TEXT,                               -- 额度单位，如 calls_per_month / prompts_per_5h / credits_in_billions
  first_month_price REAL,                        -- 首月优惠价（部分厂商有活动期首月特价），无优惠则为 NULL
  features TEXT,                                 -- 功能特性列表，JSON 数组，如 ["不限量消息","优先访问新功能"]
  -- ↓ 通用字段（所有计费类型共用）
  currency TEXT,                                 -- 币种：CNY（人民币）/ USD（美元）
  purchase_url TEXT,                             -- 购买链接（必填，硬约束），指向厂商官网购买页
  notes TEXT,                                    -- 备注信息（如 OpenRouter 的 benchmarks 元数据）
  -- ↓ 仲裁元数据（记录数据来源与置信度，便于回溯）
  confidence TEXT,                               -- 置信度：high（3源一致）/ medium（2源一致或官网兜底）/ low（单源或互差大）/ manual（人工录入）
  sources_used TEXT,                             -- 数据来源列表，JSON 数组，如 ["litellm","openrouter","adapter"]
  raw_prices_json TEXT,                          -- 原始 prices 对象完整留痕（兜底），存原始 JSON 便于字段缺失时回溯
  created_at TEXT NOT NULL,                      -- 记录创建时间 ISO8601（北京时间），精确到秒
  UNIQUE(snapshot_date, provider_id, product_id) -- 唯一约束：同一天同厂商同产品只留一条快照（重复写入用 REPLACE）
);

CREATE INDEX IF NOT EXISTS idx_snapshots_date ON price_snapshots(snapshot_date);              -- 按日期查询（如"今天所有快照"）
CREATE INDEX IF NOT EXISTS idx_snapshots_provider ON price_snapshots(provider_id);            -- 按厂商查询（如"OpenAI 全部产品"）
CREATE INDEX IF NOT EXISTS idx_snapshots_product ON price_snapshots(provider_id, product_id); -- 按产品查询历史（如"GPT-5 近 30 天价格"）

-- ========== 2. 多源原始数据留痕 ==========
-- 每个源（litellm/openrouter/adapter）的原始返回，便于仲裁失败时回溯
-- 与 price_snapshots 是 1:N 关系：一个 source 的 raw_fetch 会被仲裁为 0 或多条 snapshot
CREATE TABLE IF NOT EXISTS raw_fetches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,          -- 自增主键
  fetch_date TEXT NOT NULL,                      -- 抓取日期 YYYY-MM-DD（北京时间）
  source TEXT NOT NULL,                          -- 数据源标识：litellm（L1 主源）/ openrouter（L2 交叉源）/ adapter（L3 官网爬虫）
  provider_id TEXT NOT NULL,                     -- 厂商 ID
  raw_json TEXT NOT NULL,                        -- 原始返回 JSON（Product 对象数组序列化），保留完整字段便于回溯
  product_count INTEGER,                         -- 本次抓取返回的产品数量（冗余字段，便于快速统计）
  fetched_at TEXT NOT NULL                       -- 抓取时间 ISO8601（北京时间）
);

CREATE INDEX IF NOT EXISTS idx_raw_date ON raw_fetches(fetch_date);                  -- 按日期查询
CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_fetches(source, provider_id);       -- 按源+厂商查询（如"OpenAI 的 LiteLLM 数据"）

-- ========== 3. 价格变动审计 ==========
-- 自动 diff 今日与昨日 snapshot，记录字段级变动
-- detect_price_changes() 每日生成，用于飞书告警与历史追溯
CREATE TABLE IF NOT EXISTS price_changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,          -- 自增主键
  change_date TEXT NOT NULL,                     -- 变动检测日期 YYYY-MM-DD（北京时间）
  provider_id TEXT NOT NULL,                     -- 厂商 ID
  product_id TEXT NOT NULL,                      -- 产品 ID
  billing_type TEXT NOT NULL,                    -- 计费类型，便于按类型过滤变动
  field TEXT NOT NULL,                           -- 变动字段名，如 input_price / output_price / monthly_price / first_month_price
  old_value REAL,                                -- 旧值（昨日快照值）
  new_value REAL,                                -- 新值（今日快照值）
  change_pct REAL,                               -- 变化百分比 (new-old)/old*100；old=0 时为 NULL 或 inf
  created_at TEXT NOT NULL                       -- 记录创建时间 ISO8601（北京时间）
);

CREATE INDEX IF NOT EXISTS idx_changes_date ON price_changes(change_date);              -- 按日期查询（如"今天所有变动"）
CREATE INDEX IF NOT EXISTS idx_changes_provider ON price_changes(provider_id, product_id); -- 按产品查询变动历史

-- ========== 扩展预留 ==========
-- 后续新增表（如用户 token 资产 user_token_assets、告警记录 alert_logs）在此追加
