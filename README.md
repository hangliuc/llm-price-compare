# PPK · Price Per Token

PPK 聚合主流 AI Provider 的 Token 价格、通用订阅与 Coding Plan，并提供价格比较与历史追踪。

## 本地运行

先生成 V2 数据，再启动前端：

```bash
python3 -m scripts.pipeline_v2.cli run --profile full-verify
python3 -m http.server 4173
```

访问 `http://localhost:4173/ui/`。

生产环境读取 `/data/v2/catalog.json`；使用仓库根目录的 Python Server
时，前端会自动读取 `runtime/v2/public/v2/catalog.json`，无需复制文件。

执行测试：

```bash
python3 -m pytest -q
```

## 数据 Pipeline

数据更新由短生命周期 V2 Pipeline 完成：采集、归一化、身份解析、字段仲裁、校验、异常保护、不可变版本保存，最后原子替换生产环境的 `runtime/public/v2/catalog.json`。前端读取 V2 Catalog，数据更新不需要重建 Web 容器。

```bash
python3 -m scripts.pipeline_v2.cli run --profile full-verify
python3 -m scripts.pipeline_v2.cli status
python3 -m scripts.pipeline_v2.cli release list
python3 -m scripts.pipeline_v2.cli review list
python3 -m scripts.pipeline_v2.cli maintenance retention --dry-run
```

V1 `run_daily.py`、旧 SQLite 与 `data/prices.json` 发布路径已经删除。更新过程不执行 `git commit` / `git push`，也不需要重建 Web 容器。

服务器使用 systemd timer 调用一次性 Compose 任务：

```bash
docker compose --profile pipeline run --rm pipeline-v2 run --profile full-verify
docker compose --profile pipeline run --rm pipeline-v2 status
```

完整架构、调度、发布、告警、运维和迁移说明见 [docs/data-pipeline.md](docs/data-pipeline.md)。部署步骤见 [DEPLOY.md](DEPLOY.md)。

## 主要目录

```text
data/
  manual/                  人工数据与明确 Override
  identity/                模型 Canonical ID 与别名规则
scripts/
  sources/                 聚合数据源
  adapters/                Provider 官网采集适配器
  core/                    领域模型与 Reconcile
  pipeline_v2/             V2 数据 Pipeline
  tests/                   单元与集成测试
ops/systemd/               外部调度配置
ui/                        静态前端
docs/data-pipeline.md      数据链路设计与运维文档
```

## 数据持久化

- `runtime/public/v2/catalog.json`：生产 Nginx 直接提供给前端的原子发布文件。
- `runtime/public/v2/status.json`：当前公开 Release 的健康摘要。
- `runtime/v2/prices-v2.db`：运行、来源、决策、Review、Release、Change 和 Alert 审计库。
- `runtime/v2/releases/`：V2 自己生成的不可变发布版本和回滚基线。
- `runtime/v2/raw/objects/`：gzip Raw Evidence / 规范化证据快照，按 SHA-256 去重。
- `data/manual/*.yaml`：版本控制内的人工来源与 Override。

生产 Compose 将 `./data` 同时提供给 Pipeline 与 Web，并将 `./runtime` 持久化至 Pipeline 的 `/var/lib/ppk`。

## License

MIT
