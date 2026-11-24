# TaskList 模块规格

管理项目内的任务清单：把已冻结的测试点修订组织成一份可执行的有序清单。

## 概念

清单（TaskList）是一个聚合：负责维护状态、修订号、条目顺序和内容指纹。

清单条目引用测试点的一条修订，标识是 `(testpoint_id, revision_ver)`；对于任一测试点下修订号在用例库中全局唯一。条目在加入清单时固定修订，之后不再改写。`project_version` 只表示本次测试针对的项目版本，不参与条目标识。

清单的状态只有草稿（`DRAFT`）和已锁定（`LOCKED`）两种。锁定后条目与内容指纹不可变，只有标题仍可修改。

## 对外部模块的依赖

清单自己定义三个只读端口，不引用用例库、Access 或结果系统的实现。

* `ProjectVersionLookup.project_version_exists(project_id, proj_ver)`：向 Access 确认项目版本存在。由集成层的 `AccessProjectVersionLookup` 实现，在创建/复制清单之前调用。
* `TestPointLibraryPort`：`resolve_revisions`、`get_revisions`、`get_testpoint_briefs`、`get_testpoint_payload`。用于解析修订、判断存在性、读取实现正文并计算内容指纹。
* `RunHistoryPort`：`get_last_results`、`get_duration_stats`。可选，只供 `preview` 展示最近结果与耗时估算；任务清单永远不写结果系统。

## 写操作

以下写操作都返回读模型或结构化反馈。

* `CreateTaskList(project_version, tasklist_title)` 创建草稿。`project_version` 必填并规范化为 `v0.1` 形式；Access 中不存在该版本时拒绝。版本字段形如 `v0.1`、`v0.9`、`v0.10`。
* `CopyTaskList(source_tasklist_id, project_version, mode)` 从已有清单复制一份新草稿。`mode` 是 `RERESOLVE` 或 `PINNED`；新项目版本同样必须存在。
* `LockTaskList(tasklist_id)` 锁定草稿：校验非空 → 引用可查 → 内容指纹未漂移 → 固化清单指纹。
* `AddItems(tasklist_id, testpoint_ids, pin_versions)` 批量加入条目。`pin_versions` 可选，按 `{testpoint_id: revision_ver}` 指定修订；未指定的按项目版本解析。
* `RemoveItems(tasklist_id, testpoint_ids)` 按 `testpoint_id` 删除条目，不重排 `seq`。
* `RenameTaskList(tasklist_id, tasklist_title)` 修改标题。锁定后仍可改，不影响修订号与内容指纹。

`AddItems` 的条目级失败（重复、不存在、无可用修订、pin 不存在）不抛异常，而是放进返回值的 `rejected`。整批编辑只让 `rev` 加一。

## 读接口

读接口返回不可变的读模型，字段是模块契约的一部分：新增字段兼容，改名或改变语义是破坏性变更。

* `get_tasklist(tasklist_id)` 返回清单元数据、`item_count` 和有序条目。条目带 `seq`、`testpoint_ref`（`testpoint_id`、`revision_ver`、`title`、`content_hash`、`pinned`）和当前标题。执行、锁定和内容指纹都以 `testpoint_ref.revision_ver` 为准。
* `preview_tasklist(tasklist_id, view, page, page_size)` 返回 `summary` 与 `diagnostics`。`view` 只允许 `full` 或 `summary`；`full` 额外返回分页条目。条目带 `flags`、`last_run`（`revision_ver`、`status`、`run_at`、`stale`）、`duration_median_ms` 和 `latest_frozen_revision`。`latest_frozen_revision` 是读取时按当前用例库规则解析出的最新已冻结修订，只用于诊断，不写回清单。`summary` 含 `item_count`、`est_total_sec`、`duration_unknown_count`。
* `list_tasklists(status)` 按创建时间列出当前项目的清单摘要；`status` 可选 `DRAFT` / `LOCKED`。
* `export_testpoints(tasklist_id)` 按 `seq` 顺序返回实现正文，供执行器使用。只允许已锁定清单。

`preview` 只报告问题，不拦截；拦截发生在 `lock`。诊断项包括引用修订不存在、内容指纹变化、项目版本下无可用修订、存在更新的修订、上次结果已过期、耗时未知。

## 事件

暂无发出，也暂无订阅。

## 错误

所有错误继承 `TaskListError` 并带稳定 `code`：

* `InvalidArgument`（`INVALID_ARGUMENT`）参数形状不合法
* `ProjectVersionMissing`（`PROJECT_VERSION_MISSING`）创建清单时未指定项目版本
* `ProjectVersionNotFound`（`PROJECT_VERSION_NOT_FOUND`）Access 中没有该项目的该版本
* `ListNotFound`（`LIST_NOT_FOUND`）清单不存在，或不属于当前项目
* `ListLocked`（`LIST_LOCKED`）对已锁定清单做编辑
* `EmptyList`（`EMPTY_LIST`）空清单不允许锁定
* `DuplicateItem`（`DUPLICATE`）同一清单内测试点重复
* `ListNotLocked`（`LIST_NOT_LOCKED`）导出要求清单已锁定

条目级失败使用同一组错误码，但放在 `rejected` 里而不是抛出：

* `DUPLICATE`、`TESTPOINT_NOT_FOUND`、`NO_APPLICABLE_REVISION`、`REVISION_NOT_FOUND`

`SUPERSEDED`、`TESTPOINT_CONTENT_CHANGED` 也可能作为 `preview` 的警告或错误出现。

## 规则

1. 状态只能 `DRAFT → LOCKED` 单向变化，不可撤销。
2. 同一清单内 `testpoint_id` 唯一。
3. 条目在加入那一刻固定 `(testpoint_id, revision_ver, content_hash)`，之后不改写。
4. `rev` 只在有实际条目变化的成功编辑时加一；`rename` 不加，`lock` 不加。
5. 锁定要求清单非空，且每个引用的修订仍可读、内容指纹与加入时一致。
6. 锁定后条目和内容指纹不可变；标题仍可修改。
7. 创建与复制清单前必须确认项目版本存在；版本一旦写入清单不再变化。
8. `RERESOLVE` 在复制那一刻完成解析并写入新草稿，并不推迟到锁定；`PINNED` 保留来源修订，若新项目版本与来源不同则给出警告。
9. 清单内容指纹覆盖“项目版本 + 有序的 `(testpoint_id, revision_ver, content_hash)`”。标题、状态、`rev`、`pinned` 不进入指纹；顺序进入指纹。
10. 测试点的内容指纹由 TaskList 自己计算：读取实现正文后做规范化 JSON 摘要。
11. 加入条目时逐条判断，失败进 `rejected`，不会中断整批条目添加。
12. 清单属于且只属于一个项目，仓储按 `proj_id` 隔离。
13. 最近结果与耗时只用于 `preview` 展示；任务清单不写结果库，缺省端口时这三项展示为空。
14. `get_tasklist` 只返回清单冻结的内容，不做版本解析；`latest_frozen_revision` 只出现在 `preview` 的诊断里，不写回清单，也不影响锁定与执行。

实现位置：`stsd/tasklist/`。应用入口：`TaskListApp`，每个操作接收一个命令对象，例如 `ctx.tasklist.create_tasklist(CreateTaskList(...))`。
