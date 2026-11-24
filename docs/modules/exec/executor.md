# 执行器模块规格

> 状态：目标设计，尚未实现。

领取已启动的任务，运行修订的实现，产出执行结果。不关心任务和用例是怎么建立的。本文是对外契约，内部设计见 [internals.md](internals.md)。

## 写操作

*   `ExecTask(actor_id, task_id)` 把任务排入执行队列，不等它跑完
*   `ExecTestCaseForTest(actor_id, testpoint_id, revision_ver)` 同步运行单条修订，直接返回结果

## 读依赖

执行一个任务要读四样东西，各自独立事务：Task 的 `get_task_detail` 取清单，用例库的 `get_testpoint_detail` 取各修订的实现声明，`get_implementation_files` 取文件内容，Access 的项目读接口取绑定的值。

执行器不碰用例库的文件存储，只通过读接口取内容。

## 事件

订阅 `TaskStarted`，发出 `TaskExecCompleted`，载荷见 [contracts/events.md](../../contracts/events.md)。

订阅处理只做一件事：往队列表插一行 `task_id`，`task_id` 上的唯一约束兜幂等，然后立刻返回。真正的执行发生在队列另一头——总线是进程内同步的，在订阅里跑容器会让 `StartTask` 的调用方一直等着。

事件在发布方 commit 之后才发，和这次插入不在同一个事务里，所以 worker 启动时和定期要扫一遍"已启动但没有队列行"的任务补齐。

## 规则

1.  任务清单里只有已冻结的修订，内容不可变，因此执行时读到的实现不会在运行中被改动，见 [decisions/005](../../decisions/005-module-interaction.md)。
2.  被测地址等绑定在执行时填入，不在实现里，见 [decisions/008](../../decisions/008-implementation-binding-not-frozen.md)。实际用的值随结果一起交出去。
3.  每条修订的结论以 `(task_run_id, testpoint_id, revision_ver)` 为键单独落库，写入幂等。任务重试时跳过已到终态的修订，见 [decisions/009](../../decisions/009-execution-work-unit.md)。
4.  一条修订的实现可能包含多个测试函数。明细原样保留，修订级结论按"有 error 则 error，有 failed 则 failed，否则 passed"收敛。
5.  `ExecTestCaseForTest` 可以针对草稿修订，用于冻结前验证实现。它的结果直接返回给调用方，不属于任何任务，也不交给结果系统保存。
