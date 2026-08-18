# 部署与运维

## 架构

- `web`：常驻 Nginx，读取只读挂载的 `./ui` 和 `./data`。
- `pipeline`：一次性任务，只读 `./data/manual`，写 `./runtime/public/prices.json` 与 `./runtime/prices.db`。
- `systemd timer`：服务器调度器；业务容器内部没有 cron。

数据发布不依赖 Git、CI/CD 或 Web 重建。Pipeline 用同目录临时文件和 `os.replace` 原子更新 `runtime/public/prices.json`，Nginx 下一次请求即可读取新版本。实时发布目录不受 Git 跟踪，因此不会阻塞后续代码部署。

GitHub Pages 只保留代码发布时的静态预览快照，不承担实时数据更新；生产实时数据由服务器 Nginx 的共享 volume 提供。

## 首次部署

```bash
git clone git@github.com:hangliuc/llm-price-compare.git /root/llm-price-compare
cd /root/llm-price-compare
mkdir -p data runtime
mkdir -p runtime/public
cp data/prices.json runtime/public/prices.json
docker compose up -d --build web
docker compose --profile pipeline build pipeline
```

如实际目录不是 `/root/llm-price-compare`，同步修改 `ops/systemd/ppk-data-pipeline.service` 的 `WorkingDirectory`。

安装外部调度：

```bash
sudo cp ops/systemd/ppk-data-pipeline.service /etc/systemd/system/
sudo cp ops/systemd/ppk-data-pipeline.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ppk-data-pipeline.timer
systemctl list-timers ppk-data-pipeline.timer
```

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
docker compose --profile pipeline run --rm pipeline run
docker compose --profile pipeline run --rm pipeline status
```

本地也可直接运行：

```bash
python3 -m scripts.pipeline.cli run
python3 -m scripts.pipeline.cli status
```

Pipeline 使用非阻塞文件锁；已有任务运行时，第二次执行不会并发覆盖数据。

## 日志与状态

```bash
systemctl status ppk-data-pipeline.timer
systemctl status ppk-data-pipeline.service
journalctl -u ppk-data-pipeline.service -n 200 --no-pager
journalctl -u ppk-data-pipeline.service -f
```

结构化任务、Source、Provider、Release 和 Change 状态位于 `runtime/prices.db`；便捷状态快照位于 `runtime/public/run_status.json`。前端仍通过 `/data/prices.json` 消费数据，宿主机发布物位于 `runtime/public/prices.json`。

## 代码发布

代码变更仍可通过 GitHub Actions/SSH 部署。部署流程只更新代码、构建 Pipeline 镜像并启动/更新 Web；价格数据变更本身不会触发 Workflow。

```bash
git pull origin master
docker compose --profile pipeline build pipeline
docker compose up -d --build --remove-orphans web
```

## 回滚与故障处理

- 采集失败或校验失败：旧 `prices.json` 保持不变。
- 单 Provider 异常：候选回退该 Provider 的 Last Known Good，并标记 stale。
- 发布后历史/告警记录失败：已发布 JSON 不回滚，状态记录 warning。
- 误发布：从 SQLite 最近的 `pipeline_releases.payload_json` 导出审核后的版本，再通过原子写方式恢复；不要直接编辑正在服务的 JSON。
- Web 未看到新数据：比较宿主机 `runtime/public/prices.json` 与 `/data/prices.json` HTTP 响应，并检查 Compose volume。

更完整的架构与排障说明见 [docs/data-pipeline.md](docs/data-pipeline.md)。
