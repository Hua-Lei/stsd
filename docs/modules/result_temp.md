# 结果系统模块规格

> 状态：已实现（同步记录）；

接收一次执行的结果并保存，提供读取与对比。

## 写操作

* `RecordExecution(snapshot, outcome, environment_name, base_url, timeout_seconds, kind, source_run_id)` 保存一次已经完成的执行。执行器返回 `aborted`，或结果与快照对不上时，RunRecord 记为 `ABORTED`，不向入口层抛错。
* `RecordAbortedExecution(snapshot, error_message, environment_name, base_url, timeout_seconds, kind, source_run_id)` 在执行器整体抛错时保留一条可查的 `ABORTED` RunRecord。
* `RecordRun(run)` 直接保存外部已经构造好的 RunRecord。

写入完成后结果不可修改。

## 读依赖

* `TaskListSnapshotPort.get_snapshot(tasklist_id)`：读取锁定清单的元数据和有序实现正文。由 `TaskListSnapshotAdapter` 包装 TaskList 的 `get_tasklist` 与 `export_testpoints`；未锁定、缺正文或条目数不一致时报错。结果系统只读清单，不修改它。

结果系统不调用执行器，也不导入执行器实现。结果读模型同时供分析模块使用：集成层把 `GetRun` 的结果转成 `RunEvidence`，交给分析模块的 `RunReadPort`；分析模块不读结果仓储。

## 读接口

* `GetRun(run_id, include_steps)` 返回 RunRecord 元数据、汇总和逐条结果。逐条结果带 `seq`、`testpoint_id`、`revision_ver`、`content_hash`、`title`、`status`、`error_type`、`message`、`duration_ms`、首个失败步骤摘要；`include_steps` 为真时另带完整步骤证据和 `testpoint_snapshot`。
* `ListRuns(tasklist_id, limit)` 按开始时间倒序返回摘要，不加载逐条结果。
* `CompareRuns(base_run_id, variant_run_id)` 按 `testpoint_id` 对齐两次 RunRecord，返回两边的状态、修订号、错误类型和 `changed` 标记。

## 结果对象

* RunRecord：一次执行，引用锁定清单的 `tasklist_id`、`rev`、`content_hash`，并保存项目版本、执行环境、汇总和逐条结果。
* TestPointResult：某个测试点在一次 RunRecord 中的结论，附带逐步骤证据和执行时的实现正文快照。
* StepResult：步骤级证据，包含请求、响应、断言、提取变量、错误类型和耗时。

RunRecord 的状态是 `RUNNING`、`SUCCEEDED`、`FAILED`、`ABORTED`。测试点级只有 `passed`、`failed`、`error`；`skipped` 只出现在步骤级。

## 事件

暂无发出，也暂无订阅。目标设计中的 `TaskExecCompleted` 尚未接入，当前由 Workflow 同步调用 `RecordExecution`。

## 错误

所有错误继承 `ResultError` 并带稳定 `code`：

* `RunNotFound`（`RUN_NOT_FOUND`）RunRecord 不存在，或不属于当前项目
* `SnapshotMismatch`（`SNAPSHOT_MISMATCH`）清单条目数与导出正文数不一致
* `InvalidExecution`（`INVALID_EXECUTION`）执行器结果与快照对不上：数量不一致、`seq` 不存在、测试点不一致
* `InvalidArgument`（`INVALID_ARGUMENT`）参数形状或枚举值不合法

`PROJECT_SCOPE` 是预留错误码，当前由仓储把跨项目访问折叠为“不存在”，不单独抛出。

## 规则

1. RunRecord 写入后不可修改；状态只能从 `RUNNING` 进入 `SUCCEEDED`、`FAILED` 或 `ABORTED`。
2. RunRecord 记录锁定清单的 `tasklist_id`、`tasklist_rev`、`tasklist_content_hash` 与 `project_version`，用于追溯执行的是哪一份内容。
3. 写完结果前校验：结果数量必须等于快照条目数，`seq` 必须存在，测试点 id 必须一致，`testpoint_id` 与 `seq` 都不得重复。
4. 汇总字段是 `total`、`passed`、`failed`、`error`、`skipped_steps`、`duration_ms`；`skipped_steps` 只统计步骤。
5. 任一条 `failed` 或 `error`，整次 RunRecord 记为 `FAILED`；全部通过才记为 `SUCCEEDED`。
6. `ABORTED` 保留 `error_message`，可以没有逐条结果；`total` 仍按快照条目数记录。
7. 每条结果保存执行时的实现正文快照（`testpoint_snapshot`），之后用例库修改不影响历史。
8. 结果按 `proj_id` 隔离；其他项目的 RunRecord 视为不存在。
9. `ListRuns` 只读汇总，不加载逐条结果与步骤证据。
10. 比较两次 RunRecord 时按 `testpoint_id` 对齐，不依赖 `seq`。
11. 分析包、报告和建议不属于本模块；结果系统只提供读模型，不保存分析报告。

实现位置：`stsd/results/`。应用入口：`ResultsApp`，每个操作接收一个命令对象，例如 `ctx.results.get_run(GetRun(...))`。
