# 结果系统模块规格

> 状态：目标设计，尚未实现。

接收执行结果并保存。分析能力暂不展开，当前阶段保证结果能被存储和读取。

## 读接口

*   `get_task_result(task_id)`

## 事件

订阅 `TaskExecCompleted`，收到后保存其中的执行结果，载荷见 [contracts/events.md](../contracts/events.md)。暂无发出。

逐条结果要保存执行时实际用的绑定，否则没法解释一条旧结果当时打的是哪个环境，见 [decisions/008](../decisions/008-implementation-binding-not-frozen.md)。
