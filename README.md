# stsd-demo

LLM 辅助的 Web API 测试管理平台。

## Docker 部署

需要宿主机有 Docker 和 Docker Compose。worker 用 Python Docker SDK 启动
测试容器，因此容器内挂载宿主机的 docker socket。

```bash
cp .env.example .env
# 编辑 .env，填入已有的 STSD_PROJECT_ID
docker compose build
docker compose up -d
docker compose logs -f worker
```

`STSD_PROJECT_ID` 是 worker 负责的项目 id；执行器按项目装配 TaskList 读接口，
不同项目需要各自一个 worker。

当前还没有 HTTP API，任务入队通过 Python 调用：

```python
from stsd.bootstrap import bootstrap_executor
from stsd.config import get_engine, get_session_factory

engine = get_engine()
context = bootstrap_executor(get_session_factory(engine), project_id)
context.executor.exec_task(actor_id, tasklist_id)
```

worker 只负责消费队列，不提供项目、清单或任务创建接口。首次部署需要先用
现有 Python API 准备 Access、用例库和 TaskList 数据，并让 worker 使用同一个
数据库。

## 本地运行

```bash
PYTHONPATH=src .venv/bin/python -m stsd.worker
```

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `STSD_PROJECT_ID` | 必填 | worker 负责的项目 id |
| `STSD_DB_URL` | `sqlite:///stsd.db` | compose 使用 `/data/stsd.db` |
| `STSD_FILE_ROOT` | `.stsd/files` | 实现文件内容目录 |
| `STSD_WORK_ROOT` | `.stsd/exec` | 本地沙箱工作目录（Docker 运行时不用） |
| `STSD_RUNTIME` | `local` | compose 使用 `docker` |
| `STSD_DOCKER_IMAGE` | `python` | 测试容器镜像前缀，标签由 python 版本拼成 |
| `STSD_DOCKER_NETWORK` | 空 | 测试容器加入的 Docker 网络；需要访问宿主机服务时可设 `host` |
| `STSD_REVISION_TIMEOUT` | `300` | 单条修订超时秒数 |
| `STSD_LEASE_SECONDS` | `60` | 队列租约秒数 |
| `STSD_POLL_INTERVAL` | `1` | worker 空转轮询间隔 |

## 说明

- 挂载 `/var/run/docker.sock` 等于把宿主机 Docker 控制权交给 worker，
  只应在受信任的部署环境使用。
- 测试容器使用 `python:<版本>-slim`，首次运行会拉取镜像。
- 当前数据库是 SQLite，适合单 worker；多 worker 抢占应换 Postgres。
- 结果系统、TaskStarted 订阅和 HTTP API 尚未接入，见 `docs/STATUS_AND_ROADMAP.md`。
