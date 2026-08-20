# 部署与运维

## 架构

- `web`：常驻 Nginx，只读挂载 `ui/` 与 `runtime/public/`。
- `pipeline`：一次性 V3 任务，读取 Models.dev 和厂商官方套餐页面。
- `ppk-data-pipeline.timer`：宿主机调度器，容器内部没有 cron。

Pipeline 成功后先保存不可变 Release，再用 `os.replace` 原子更新 `runtime/public/catalog.json` 与 `status.json`。失败运行不会覆盖当前正式数据。

## 首次部署

```bash
git clone git@github.com:hangliuc/llm-price-compare.git /root/llm-price-compare
cd /root/llm-price-compare
mkdir -p runtime/public runtime/releases runtime/raw
docker compose --profile pipeline build pipeline
docker compose --profile pipeline run --rm pipeline run
docker compose up -d --build web

sudo cp ops/systemd/ppk-data-pipeline.service /etc/systemd/system/
sudo cp ops/systemd/ppk-data-pipeline.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ppk-data-pipeline.timer
```

如代码目录不是 `/root/llm-price-compare`，修改 service 的 `WorkingDirectory`。

## 手工执行

```bash
cd /root/llm-price-compare
docker compose --profile pipeline run --rm pipeline run
docker compose --profile pipeline run --rm pipeline status
docker compose --profile pipeline run --rm pipeline probe-plans
```

`probe-plans` 会检查稳定与实验套餐来源，但不会发布。

## 正式运行后的职责边界

- GitHub Actions 负责更新代码、构建镜像、启动 Web 和安装 systemd timer。
- 只有全新服务器尚无 `catalog.json` / `status.json` 时，部署流程才执行一次初始化采集。
- 日常数据更新只由 `ppk-data-pipeline.timer` 触发，不依赖 Git push、代码部署或 Web 重建。
- Pipeline 发布失败时，Workflow、Web 和上一份成功 Catalog 都不受影响。

代码部署完成后建议执行一次只读核验：

```bash
cd /root/llm-price-compare
docker compose ps
systemctl is-enabled ppk-data-pipeline.timer
systemctl is-active ppk-data-pipeline.timer
systemctl list-timers ppk-data-pipeline.timer
python3 -m json.tool runtime/public/status.json
curl -fsS http://127.0.0.1:8001/data/status.json | python3 -m json.tool
```

本地文件与 HTTP 返回中的 `release_id` 应一致，`status` 应为 `healthy`；`summary` 中的数量应与 Catalog 实际记录数一致。

## 日志与状态

```bash
systemctl status ppk-data-pipeline.timer --no-pager
systemctl list-timers ppk-data-pipeline.timer
journalctl -u ppk-data-pipeline.service -n 200 --no-pager
journalctl -u ppk-data-pipeline.service -f
python3 -m json.tool runtime/public/status.json
```

持久化文件：

- `runtime/public/catalog.json`：前端正式数据。
- `runtime/public/status.json`：当前 Release 状态。
- `runtime/ppk.db`：任务、来源快照、Catalog 快照和 Release 记录。
- `runtime/releases/<release_id>/`：不可变发布文件。
- `runtime/raw/<run_id>/`：压缩后的原始响应。

## 故障处理

- Pipeline 失败：查看 Journal 和 `python3 -m scripts.pipeline_v3.cli status`；正式 Catalog 保持不变。
- 套餐页面变更：运行 `probe-plans` 定位 Adapter，再检查对应 `runtime/raw/<run_id>/`。
- Web 没有新数据：比较 `runtime/public/catalog.json` 与 `http://127.0.0.1:8001/data/catalog.json`，检查文件权限和 Compose volume。
- 需要恢复历史版本：从 `runtime/releases/<release_id>/catalog.json` 核对后，以原子方式恢复；不要直接编辑价格字段。

代码部署由 GitHub Actions 完成；数据定时更新独立运行，不触发代码部署。
