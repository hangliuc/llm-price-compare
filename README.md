# PPK · Price Per Token

PPK 是一个面向开发者的 AI 定价浏览与对比站。它聚合主流厂商的模型 API Token 价格、通用订阅和 AI Coding Plan，帮助你在选型前快速看清价格、市场与计费方式。

前端以静态站点形式提供服务；数据由独立 Pipeline 定期抓取、校验并原子发布，因此日常价格更新不需要重新构建或部署 Web 服务。

## 能做什么

- 浏览按需计费模型的输入、输出、缓存价格、上下文窗口与模态。
- 对比多个模型的价格；跨币种排序和比较使用发布时的人民币参考汇率，官方原币价格始终保留。
- 浏览通用订阅、开发者套餐与 Coding Plan 的月费、额度和权益。
- 区分同一模型在不同官方市场、购买渠道或服务层级下的独立报价。
- 查看数据发布时间和发布状态；采集或校验失败时，站点继续使用上一份完整成功的数据。

## 数据范围与原则

| 数据类型 | 自动来源 | 说明 |
| --- | --- | --- |
| 模型按需计费 | [Models.dev](https://models.dev/) | 国际模型目录的唯一自动来源；包含价格与模型元数据。 |
| 国内官方模型报价 | 厂商官方定价页 / API Adapter | 按目标市场独立采集，不由 IP、语言或 Cookie 推断。 |
| 订阅与 Coding Plan | 厂商官方页面 / API Adapter | 采集月费、周期、额度和权益。 |
| 汇率参考 | Frankfurter 日度汇率 | 仅用于统一比较值，不替代官方结算币种。 |

PPK 展示的是采集时可获得的官方或公开目录信息，最终价格、可用地区、税费及权益以厂商结算页为准。

## 快速开始

### 环境要求

- Python 3.11+
- 可访问数据源的网络连接
- 可选：Docker Compose（运行生产形态）

### 本地运行

安装依赖并生成一份本地 Catalog：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python3 -m scripts.pipeline_v3.cli run
python3 -m http.server 4173
```

然后访问 [http://localhost:4173/ui/](http://localhost:4173/ui/)。本地静态服务器会读取 `runtime/public/catalog.json`；首次运行 Pipeline 后该文件会自动生成。

运行测试：

```bash
python3 -m pytest -q
```

## 数据 Pipeline

Pipeline 将数据归一化为统一 Catalog，执行 Schema 与数量下降保护，保存原始响应和不可变 Release，最后以原子替换方式发布正式文件。

```bash
# 抓取、校验并发布 Catalog
python3 -m scripts.pipeline_v3.cli run

# 仅演练，不写入正式发布文件
python3 -m scripts.pipeline_v3.cli run --dry-run

# 查看最近一次运行状态
python3 -m scripts.pipeline_v3.cli status

# 检查全部套餐 Adapter，不发布
python3 -m scripts.pipeline_v3.cli probe-plans

# 检查实验性的官方按需报价 Adapter，不发布
python3 -m scripts.pipeline_v3.cli probe-official-markets
```

正常生产发布要求按需报价和套餐均达到最低数量阈值，且与上一份发布数据相比没有异常下降。任何必要来源或校验失败都会阻止发布，当前线上 Catalog 不会被覆盖。

常用可选参数：

```bash
# 使用本地 Models.dev / 汇率夹具，适合离线测试
python3 -m scripts.pipeline_v3.cli run --dry-run \
  --models-dev-file /path/to/models.json --fx-file /path/to/fx.json

# 纳入实验性的官方市场报价来源
python3 -m scripts.pipeline_v3.cli run --official-markets
```

## Docker 与生产部署

Web 容器通过 Nginx 暴露静态前端和发布数据，Pipeline 容器按需执行一次采集任务：

```bash
# 首次运行前创建运行目录
mkdir -p runtime/public runtime/releases runtime/raw

# 构建并执行一次数据采集
docker compose --profile pipeline build pipeline
docker compose --profile pipeline run --rm pipeline run

# 启动站点，默认监听 http://localhost:8001/ui/
docker compose up -d --build web
```

服务器推荐使用 `ops/systemd/ppk-data-pipeline.timer` 在每天 07:00 与 19:00（Asia/Shanghai）触发 Pipeline。完整的安装、巡检、日志和恢复说明见 [DEPLOY.md](DEPLOY.md)。

## 运行产物

运行时数据不会提交到 Git：

```text
runtime/public/catalog.json      前端读取的当前正式 Catalog
runtime/public/status.json       当前发布状态与摘要
runtime/v3/ppk.db                运行记录、来源快照与发布记录（容器中为 runtime/ppk.db）
runtime/v3/releases/             本地不可变 Release（容器中为 runtime/releases）
runtime/v3/raw/                  本地原始响应快照（容器中为 runtime/raw）
```

具体路径可通过 `PPK_RUNTIME_DIR`、`PPK_PUBLIC_DIR`、`PPK_DB_PATH`、`PPK_CATALOG_PATH` 等环境变量覆盖；Docker Compose 已提供生产环境对应配置。

## 项目结构

```text
ui/                              Vue 3 静态前端
scripts/pipeline_v3/             数据模型、抓取、归一化、校验、存储与发布
scripts/pipeline_v3/sources/     Models.dev、官方报价及套餐 Adapter
scripts/tests/                   Pipeline 自动化测试
ops/systemd/                     生产环境定时任务配置
docs/                            数据范围、设计和来源覆盖审计
```

## 相关文档

- [V3 数据获取与发布架构](docs/data-pipeline-lite-v3-proposal.md)
- [V3.1 官方原币与多市场报价设计](docs/v3.1-native-currency-and-market-pricing.md)
- [数据源覆盖率审计](docs/data-source-coverage-audit.md)
- [部署与运维手册](DEPLOY.md)

## License

MIT
