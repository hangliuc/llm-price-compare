# 部署与运维

## 架构

- `web`：常驻 Nginx，读取只读挂载的 `./ui` 和 `./runtime/public`。
- `pipeline-v2`：一次性任务，只读人工数据与 Identity 配置，写 V2 Catalog、状态和审计库。
- `systemd timer`：服务器调度器；业务容器内部没有 cron。

数据发布不依赖 Git、CI/CD 或 Web 重建。Pipeline 先保存不可变 Release，再用 `os.replace` 原子更新 `runtime/public/v2/catalog.json` 和 `status.json`，Nginx 下一次请求即可读取新版本。

GitHub Pages 只保留代码发布时的静态预览快照，不承担实时数据更新；生产实时数据由服务器 Nginx 的共享 volume 提供。

## 首次部署

```bash
git clone git@github.com:hangliuc/llm-price-compare.git /root/llm-price-compare
cd /root/llm-price-compare
mkdir -p runtime/public/v2 runtime/v2/releases
docker compose --profile pipeline build pipeline-v2
docker compose --profile pipeline run --rm pipeline-v2 run --profile full-verify
docker compose up -d --build web
```

如实际目录不是 `/root/llm-price-compare`，同步修改三个 `ops/systemd/ppk-v2-*.service` 的 `WorkingDirectory`。

安装外部调度：

```bash
sudo cp ops/systemd/ppk-v2-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ppk-v2-payg.timer ppk-v2-plans.timer ppk-v2-full-verify.timer
systemctl list-timers 'ppk-v2-*'
```

Phase 6 首次部署会在 V2 `full-verify` 成功后停用并删除旧
`ppk-data-pipeline` unit，同时删除宿主机 `runtime/prices.db*` 与旧锁文件。
`runtime/v2/`、V2 Release 和 V2 审计库不会被删除。

默认每天北京时间 05:00、11:00、17:00、23:00 运行，并带最多 120 秒随机延迟。修改频率只需编辑 timer 并执行 `daemon-reload` 与 `restart`，无需修改采集代码。

## 配置

可选环境变量写入服务器 `.env`：

```dotenv
FEISHU_WEBHOOK_URL=
PPK_PROVIDER_MIN_RATIO=0.50
PPK_DATASET_MIN_RATIO=0.70
PPK_MIN_PROVIDERS=3
PPK_MIN_PRODUCTS=20
```

路径变量已在 Compose 中映射到共享持久化目录。不要为 Pipeline 配置 Git Token。

## 手工执行

```bash
cd /root/llm-price-compare
docker compose --profile pipeline run --rm pipeline-v2 run --profile full-verify
docker compose --profile pipeline run --rm pipeline-v2 status
docker compose --profile pipeline run --rm pipeline-v2 alerts
docker compose --profile pipeline run --rm pipeline-v2 release list
```

本地也可直接运行：

```bash
python3 -m scripts.pipeline_v2.cli run --profile full-verify
python3 -m scripts.pipeline_v2.cli status
```

Pipeline 使用非阻塞文件锁；已有任务运行时，第二次执行不会并发覆盖数据。

## 日志与状态

```bash
systemctl status ppk-v2-payg.timer ppk-v2-plans.timer ppk-v2-full-verify.timer
journalctl -u ppk-v2-payg.service -n 200 --no-pager
journalctl -u ppk-v2-payg.service -f
```

结构化任务、Source、Decision、Review、Release、Change 和 Alert 位于 `runtime/v2/prices-v2.db`；运行结果位于 `runtime/public/v2/run_status.json`。前端通过 `/data/v2/catalog.json` 消费数据。

## 代码发布

代码变更仍可通过 GitHub Actions/SSH 部署。部署流程只更新代码、构建 Pipeline 镜像并启动/更新 Web；价格数据变更本身不会触发 Workflow。

```bash
git pull origin master
docker compose --profile pipeline build pipeline-v2
docker compose up -d --build --remove-orphans web
```

## 回滚与故障处理

- 采集失败或校验失败：当前 V2 Catalog 保持不变。
- 单 Provider 异常：候选回退该 Provider 的 Last Known Good，并标记 stale。
- 发布后历史/告警记录失败：已发布 JSON 不回滚，状态记录 warning。
- 误发布：执行 `python3 -m scripts.pipeline_v2.cli release list`，再执行 `python3 -m scripts.pipeline_v2.cli release rollback <release_id>`；不要直接编辑正在服务的 JSON。
- Web 未看到新数据：比较宿主机 `runtime/public/v2/catalog.json` 与 `/data/v2/catalog.json` HTTP 响应，并检查 Compose volume 和文件权限。

更完整的架构与排障说明见 [docs/data-pipeline.md](docs/data-pipeline.md)。
