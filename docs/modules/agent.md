# Agent 模块规格（待定）

长流程生成器。生成的内容经人工审批后才进入用例库。本模块的设计尚未确定，下面保留的是此前讨论的草稿，不作为实现依据。

## 写操作

*   `GenerateTestPoint(actor_id, project_id, prompt)` 启动异步生成
*   `ApproveOperation(actor_id, operation_id)` 人工审批同意
*   `RejectOperation(actor_id, operation_id)` 拒绝

## 事件

草稿中发出 `TestPointGenerated(target_section_id, testpoint_data)`，审批同意后通知用例库落库。

## 待定的问题

1.  审批通过后，是由用例库订阅事件落库，还是由 Agent 直接调用用例库的写操作。后一种做法让用例库不需要知道 Agent 的存在，人和 Agent 走同一条写入路径，但这一点尚未决定。
2.  用例分析中的 G2（分析当前变更）还没有对应的命令，事件也只覆盖新建测试点，没有覆盖对已有测试点的修订。
3.  Agent 的审批与用例库的 `AuditAndFreeze` 是两次人工确认，二者的分工需要说明。
4.  新修订的实现为空，如何由 Agent 产出实现，也需要设计。
