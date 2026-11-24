# Workflow 模块规格

把锁定清单、执行器和结果系统串成一次同步执行：读取快照、执行、记录结果。

## 概念

Workflow 不是业务聚合，也没有自己的持久化。它只表达一个编排用例：给定一份锁定清单，跑一次，把结果交给结果系统。

它依赖三个端口：

* 清单快照：确定执行内容和执行顺序；
* 执行器：确定具体执行实现；
* 结果记录：确定执行结果如何处理。

执行是同步的：调用方等待执行结束，拿到结果系统返回的读模型。没有任务状态机、事件总线或后台队列。

## 对外部模块的依赖

* `TaskListSnapshotPort.get_snapshot(tasklist_id)`：读取已锁定清单的元数据与有序实现正文。快照端口负责拒绝未锁定清单。
* `ExecutorPort.execute(plan)`：执行一组测试点，返回 `ExecutionOutcome`。实现不能写结果库。
* `ResultRecorderPort.record_execution(...)` / `record_aborted_execution(...)`：把执行结果或中止原因交给结果系统。实现由结果模块的适配器提供。

依赖方向是“Workflow → 端口 ← 实现”，Workflow 不 import 任务清单或结果模块的服务函数。

## 操作

* `RunTaskList(tasklist_id, environment_name, base_url, headers, variables, timeout_seconds, kind, source_run_id)` 执行一份锁定清单。

执行步骤固定：

1. 通过快照端口读取清单；
2. 把快照条目按 `seq` 顺序转成 `ExecutionPlan`；执行环境由 `base_url`、`headers`、`variables`、`timeout_seconds` 组成，`headers` / `variables` 缺省为空，超时缺省 6 秒；
3. 调用执行器；
4. 正常结束 → `record_execution`；执行器抛异常 → `record_aborted_execution`，错误消息为 `异常类型: 内容`。

`kind` 与 `source_run_id` 原样传给结果系统，用于结果分组与溯源。

## 输出

返回结果系统给出的读模型：

* 正常执行：RunRecord 的元数据、汇总和逐条结果（是否包含步骤由结果系统决定）；
* 执行器整体失败：一条 `ABORTED` RunRecord，带 `error_message`。

Workflow 不额外加工结果，也不缓存执行结果。

## 事件

暂无发出，也暂无订阅。目标设计中执行器可订阅 `TaskStarted`，当前实现由 Workflow 同步调用执行器。

## 错误

Workflow 没有自己的错误码。错误来源与处理：

* 快照读取失败（未锁定、缺正文、条目数不一致）直接抛结果模块的错误，不执行；
* 执行器异常被捕获，转成 `ABORTED` RunRecord，不向调用方抛错；
* 结果记录失败（仓储错误、参数不合法）向上抛出结果模块的错误。

## 规则

1. 只能执行锁定清单；未锁定清单由快照端口拒绝。
2. 执行顺序就是清单的 `seq` 顺序，Workflow 不重排。
3. 快照在读取后视为不可变，执行期间不再回读清单。
4. 执行器整体抛异常时仍要留下一条可查的 `ABORTED` RunRecord。
5. 单条测试点的失败由执行器表达为结果，不是 Workflow 的异常。
6. Workflow 不解析请求、不做断言、不判断业务正确性。
7. Workflow 不写任何存储；持久化只发生在结果记录端口内部。
8. Workflow 不知道任务清单、执行器、结果系统的具体实现，只认端口。

实现位置：`stsd/workflow/`。应用入口：`ctx.workflow.run_tasklist(RunTaskList(...))`；底层也可以直接调用 `run_tasklist(recorder, snapshot_port, executor, command)`。
