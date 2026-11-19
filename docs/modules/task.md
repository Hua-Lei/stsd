# Task 模块规格

> 状态：目标设计，尚未实现；`src/stsd/tasklist` 是旧设计草稿，待重写。

把已冻结的修订组装成任务清单，保存后可以启动。

## 写操作

*   `CreateTask(actor_id, project_id, proj_ver)`，`proj_ver` 是本次测试针对的项目版本
*   `AddTestToTask(actor_id, task_id, testpoint_id, revision_ver)`
*   `SaveTask(actor_id, task_id)` 保存并冻结任务清单
*   `StartTask(actor_id, task_id)` 启动任务，发出 `TaskStarted`

## 读接口

*   `get_task_detail(task_id)` 返回任务的 `proj_ver` 和 `(testpoint_id, revision_ver)` 列表

## 事件

发出 `TaskStarted(actor_id, task_id)`，暂无订阅。

## 规则

1.  加入任务时调用用例库的读接口，确认该修订已冻结且所属测试点未删除，否则拒绝。
2.  任务的 `proj_ver` 表示本次测试针对的项目版本，加入的修订不要求与它一致。
3.  任务里保存的始终是具体的修订号。用户没有指定修订时，调用方先通过用例库读接口取得该测试点最新的已冻结修订号，再调用 `AddTestToTask`。
4.  任务保存之后内容不可再变，只有已保存的任务才能启动。
