# PPK · Price Per Token

PPK 聚合主流 AI Provider 的 Token 价格、通用订阅与 Coding Plan，并提供价格比较与历史追踪。

## 本地运行

启动前端：

```bash
python3 -m http.server 4173
```

访问 `http://localhost:4173/ui/`。

执行测试：

```bash
python3 -m pytest -q
```

## 数据 Pipeline

数据更新由短生命周期 Pipeline 完成：采集 Source / Adapter，归一化，多源仲裁，合并人工 Override，校验与异常保护，记录历史，最后原子替换生产环境的 `runtime/public/prices.json`。前端 URL 和 JSON 主结构保持兼容。

```bash
python3 -m scripts.pipeline.cli run
python3 -m scripts.pipeline.cli status
```

兼容入口 `python3 scripts/run_daily.py` 仍可使用，但仅转调新 Pipeline。更新过程不执行 `git commit` / `git push`，也不需要重建 Web 容器。

服务器使用 systemd timer 调用一次性 Compose 任务：

```bash
docker compose --profile pipeline run --rm pipeline run
docker compose --profile pipeline run --rm pipeline status
```

完整架构、调度、发布、告警、运维和迁移说明见 [docs/data-pipeline.md](docs/data-pipeline.md)。部署步骤见 [DEPLOY.md](DEPLOY.md)。

## 主要目录

```text
data/
  manual/                  人工数据与明确 Override
  prices.json              前端发布物
scripts/
  sources/                 聚合数据源
  adapters/                Provider 官网采集适配器
  core/                    领域模型与 Reconcile
  pipeline/                新数据 Pipeline
  tests/                   单元与集成测试
ops/systemd/               外部调度配置
ui/                        静态前端
docs/data-pipeline.md      数据链路设计与运维文档
```

## 数据持久化

- `runtime/public/prices.json`：生产 Nginx 直接提供给前端的原子发布文件（不受 Git 跟踪）。
- `data/prices.json`：首次部署与 GitHub Pages 使用的静态种子快照。
- `runtime/prices.db`：运行状态、Source/Provider 结果、原始采集、发布版本和变更历史。
- `data/manual/*.yaml`：版本控制内的人工来源与 Override。

生产 Compose 将 `./data` 同时提供给 Pipeline 与 Web，并将 `./runtime` 持久化至 Pipeline 的 `/var/lib/ppk`。

## License

MIT
