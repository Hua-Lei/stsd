# 事件载荷

事件表示"这件事已经发生"，由发布方的工作单元在 commit 成功之后发出。进程内实现是 `stsd.shared.events.MessageBus`，订阅者抛异常只记日志，不影响发布方。

## TaskStarted

Task 发出，执行器订阅。载荷是 `actor_id` 和 `task_id`。

事件不带任务内容。清单保存后不可变，里面只有已冻结的修订，执行时去读和此刻带上读到的是同一份东西；带内容只会让 Task 开始理解实现的形状、让事件体积随文件增长，换不来一致性（见 [decisions/005](../decisions/005-module-interaction.md)）。

## TaskExecCompleted

执行器发出，结果系统订阅。一个任务的全部修订都到终态之后发一次。

载荷是 `task_id`、`task_run_id`，以及按修订逐条列出的 `results`，每条带：

*   `testpoint_id`、`revision_ver` 标识是哪条修订
*   `status` 取 `passed`、`failed`、`error`、`not_run`
*   `detail` 平台产物解析出的明细
*   `bindings` 这次实际用的绑定值

四个状态必须分清。`failed` 是断言不通过，这是正常结论；`error` 是跑了但出错；`not_run` 是环境没建起来，根本没跑。

`task_run_id` 标识一次执行。一个任务能否重复启动还没定，带上它在不能重复的情况下是一个冗余字段，但在能重复的情况下是两次结果不混在一起的前提。
