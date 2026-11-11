# 文档模块设计草稿

## 目标

第一周定义文档数据模型和服务接口，供团队确认字段和调用方式。接入后，前端通过 API 保存和查看文档，AI 工作流按以下顺序处理需求更新。

`add_version` → `get_comparison_input` → LLM 对照两版原文 → 工作流结合用例库提出调整建议 → 人工审核

文档模块负责提供指定版本的原文。**两版文档有哪些需求变化，由 LLM 判断。** 首次建库时，工作流可以用 `get` 读取需求文档和接口说明，作为生成测试点的输入。

## 数据类型

```python
from dataclasses import dataclass
from typing import Literal

DocumentKind = Literal["requirements", "openapi"]


@dataclass(frozen=True)
class DocSnapshot:
    doc_id: str          # 同一份逻辑文档的标识，各版本共用
    version: int         # 从 1 开始，由服务端分配
    kind: DocumentKind   # 需求文档或接口文档
    text: str            # 该版完整正文


@dataclass(frozen=True)
class DocVersionSummary:
    doc_id: str
    version: int
    kind: DocumentKind
```

`DocVersionSummary` 用于文档目录与历史列表，只返回文档标识、版本号和类型。选定版本后再读取完整正文。

`DocSnapshot` 是文档模块拟提供的共享数据类型。后续计划用 SQLite 的 `document_versions` 表存储 `project_id`、`kind`、`version` 和 `text`，主键为 `(project_id, kind, version)`。`doc_id` 的生成规则在联调时确认。

## 版本控制

| 字段 | 所属模块 | 含义 |
| --- | --- | --- |
| `DocSnapshot.version` | 文档模块 | 需求文档或接口说明的保存序号 |
| `TestPointVersion.version_no` | 用例库 | 测试点所依据的上游文档版本，参考稿中为字符串 |
| `target_software_release_version` | 任务清单 | 本轮要测的软件发布版本 |
| `use_case_version` | 用例库 / 任务清单 | 用例版本，任务清单据此固定本轮要执行的用例 |

同一项目内，`requirements` 和 `openapi` 分开编号。每次成功提交都追加一版，旧版原文继续可读。第一版按每个项目、每种类型各有一份逻辑文档设计。如果一个项目需要独立管理多份同类文档，查询时需要再指定 `doc_id`。

**和用例库的对接约定。** 需求第 2 版与 OpenAPI 第 2 版可以同时存在。用例库若沿用字符串 `version_no`，建议由调用层在已明确 `doc_id` 的情况下把整数 `2` 转成字符串 `"2"`，并一起记录文档标识。引用字段及其类型需和用例库负责人确认。

**和任务清单的对接约定。** 回归补测时，由工作流明确指定比较哪两版文档，再结合上一次清单和执行结果提出建议。若要通过软件发布版本自动选择文档，需要先约定软件版本与文档版本的映射。

## 类设计&层级抽象

```text
接口层         参数校验，转发保存与查询请求
文档服务       Documents，提供版本存取和原文读取
持久层         document_versions，使用调用方传入的连接
工作流         读取两版原文，调用 LLM，结合用例库提出调整建议
```

工作流负责跨模块组合。文档服务只使用本模块的存储和共享契约。现有 `demo/generator/process.py` 可以继续用于 OpenAPI 解析与过滤，文档模块负责保存完整原文。

### 接口

以下方法在第一周的 Python 草稿中已定义参数和返回类型，方法体留待下一阶段实现。

- `add_version(project_id, kind, text) -> DocSnapshot`：校验文档类型与正文，保存新版本，返回带版本号的完整快照。需求文档与 OpenAPI 均按原文保存。
- `list_documents(project_id) -> list[DocVersionSummary]`：列出项目内的文档，每份文档返回最新版信息。项目还没有文档时返回空列表。
- `list_versions(project_id, kind) -> list[DocVersionSummary]`：列出该类文档的历史版本，按版本号从新到旧排列。尚无版本时返回空列表。
- `get(project_id, kind, version=None) -> DocSnapshot`：读取指定版本。省略 `version` 时读取最新版本。
- `get_by_ref(project_id, doc_id, version) -> DocSnapshot`：按项目、文档 ID 和版本号读取指定原文，供工作流根据用例库的引用查阅文档。
- `get_comparison_input(project_id, kind, from_version, to_version) -> tuple[DocSnapshot, DocSnapshot]`：按旧版、新版的顺序取回两份全文。两个版本号均必填。返回结果供 AI 工作流直接使用。

### HTTP API 草案

| 方法与路径 | 参数 | 返回 |
| --- | --- | --- |
| `POST /projects/{pid}/documents` | JSON 请求体 `{kind, text}` | `201`，新版本快照 |
| `GET /projects/{pid}/documents` | 路径参数 `pid` | `200`，各文档的最新版信息 |
| `GET /projects/{pid}/documents/{kind}/versions` | 路径参数 `kind` | `200`，按版本号从新到旧的历史列表 |
| `GET /projects/{pid}/documents/{kind}` | 可选查询参数 `version`，例如 `?version=2` | `200`，指定版本或最新版本的快照 |
| `POST /projects/{pid}/sessions` | 建议传 `{type: "document_comparison", kind, from_version, to_version}` | `202`，`{session_id}` |
| `GET /projects/{pid}/sessions/{sid}` | 路径参数 `sid` | `200`，会话状态与已完成的分析结果 |

会话接口由 API 与 AI 模块实现。发起分析前，工作流根据指定版本号取出两份原文。LLM 返回新增、删除或修改的要求，以及对应版本的引文。含义不明确的内容标为待确认。比如旧版写“姓名最多 50 个字符”，新版写“姓名长度上限为 100 个字符”，LLM 应指出上限从 50 调整为 100，并附上两版原文。

### 并发

版本编号的范围是 `(project_id, kind)`。实现存储时，计划在同一条 SQL 语句中计算下一版并写入，由 SQLite 串行处理写入。比较时按指定版本号读取两份原文。LLM 调用在文档写入事务之外执行。

## 错误码

| 错误码 | HTTP 状态 | 含义 |
| --- | --- | --- |
| `INVALID_ARGUMENT` | `422` | 项目 ID 或正文为空、文档类型无效、版本号缺失或无效 |
| `DOCUMENT_VERSION_NOT_FOUND` | `404` | 读取原文时找不到对应文档或指定版本 |



