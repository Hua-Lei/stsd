# 执行器模块规格

> 状态：目标设计，尚未实现。

领取已启动的任务，运行修订的实现，产出执行结果。不关心任务和用例是怎么建立的。

## 写操作

*   `ExecTask(actor_id, task_id)`
*   `ExecTestCaseForTest(actor_id, testpoint_id, revision_ver)` 直接返回单条修订的运行结果

## 读依赖

执行任务时先用 Task 的 `get_task_detail` 取得清单，再按其中的标识调用用例库的 `get_testpoint_detail` 取得各修订的实现。

## 事件

发出 `TaskExecCompleted(task_id, exec_results)`，订阅 `TaskStarted`，收到后执行对应任务。

## 规则

1.  任务清单里只有已冻结的修订，内容不可变，因此执行时读到的实现不会在运行中被改动，见 [decisions/005](../decisions/005-module-interaction.md)。
2.  `ExecTestCaseForTest` 可以针对草稿修订，用于冻结前验证实现。它的结果直接返回给调用方，不属于任何任务，也不交给结果系统保存。
