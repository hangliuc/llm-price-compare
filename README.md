# PPK · Price Per Token

PPK 聚合主流 AI Provider 的 Token 价格、通用订阅与 Coding Plan，并提供模型浏览和价格对比。

## 本地运行

```bash
python3 -m scripts.pipeline_v3.cli run
python3 -m http.server 4173
```

访问 `http://localhost:4173/ui/`。生产环境读取 `/data/catalog.json`；仓库根目录的本地 Server 自动读取 `runtime/public/catalog.json`。

执行测试：

```bash
python3 -m pytest -q
```

## 数据 Pipeline

- 按需计费：唯一自动来源为 Models.dev。
- 套餐：由各厂商官方页面 Adapter 自动采集。
- 处理：确定性归一化、Schema 校验、数量下降保护、快照和原子发布。
- 失败策略：任一必要来源或校验失败时不发布，保留最近一次完整成功 Catalog。
- 调度：服务器 systemd timer 每天 07:00、19:00 运行一次性容器。

```bash
python3 -m scripts.pipeline_v3.cli run
python3 -m scripts.pipeline_v3.cli status
python3 -m scripts.pipeline_v3.cli probe-plans
```

数据更新不依赖 Git commit、Git push、重新部署或重建 Web 容器。

## 主要目录

```text
scripts/pipeline_v3/       数据模型、Models.dev、套餐 Adapter、校验、存储与发布
scripts/tests/             Pipeline 测试
ops/systemd/               外部调度配置
ui/                        静态 Vue 前端
runtime/public/            正式 Catalog 与状态（运行时生成，不入 Git）
runtime/releases/          不可变 Release
runtime/raw/               原始响应快照
runtime/ppk.db             运行、快照与发布记录
```

详细方案见 [docs/data-pipeline-lite-v3-proposal.md](docs/data-pipeline-lite-v3-proposal.md)，部署运维见 [DEPLOY.md](DEPLOY.md)。

## License

MIT
