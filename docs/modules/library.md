# 用例库模块规格

管理项目内的用例树和测试点的修订历史。

## 概念

用例树由两种节点构成：Section 是目录，只负责组织结构；测试点（TestPoint）拥有一条按序号线性增长的修订历史。

修订（TestPointVersion）由 `(testpoint_id, revision_ver)` 标识，`revision_ver` 是测试点自己的序号，从 1 开始。修订包含名称、描述、至多一个实现，以及说明性的 `proj_ver`，后者记录这次修订针对哪个项目版本写成，不参与标识（见 [decisions/001](../decisions/001-proj-ver-is-descriptive.md)）。修订的状态是草稿或已冻结。

## 对 Access 的依赖

用例库自己定义一个小接口，只回答"某项目有没有某个 `proj_ver`"，由 Access 的 `get_project_version` 实现。用例库不直接引用 Access 的对象，只保存 `project_id` 和 `proj_ver` 的值。

## 写操作

*   `CreateSection(actor_id, project_id, parent_id, name)`
*   `AddTestPoint(actor_id, project_id, section_id, name, proj_ver)` 同时产生第一条修订，`revision_ver` 为 1，实现为空
*   `DeleteNode(actor_id, node_id)` 软删除该节点及其未删除的后代
*   `ReviseTestPoint(actor_id, testpoint_id, proj_ver, revision_detail)` 产生新的修订，实现为空
*   `AddImplementation(actor_id, testpoint_id, revision_ver, code_impl)` 只能用于草稿，可以覆盖
*   `AuditAndFreeze(actor_id, testpoint_id, revision_ver)` 把草稿冻结

## 读接口

*   `get_section_tree(project_id, section_id)` 返回该节点下未删除的直接子节点。每个节点带类型和名称，测试点另带最新修订号及其状态、最新已冻结修订号（没有则为空），使界面显示一棵树不必逐个查询详情。
*   `get_testpoint_detail(testpoint_id, revision_ver)` 返回名称、描述、实现、`proj_ver`、修订状态，以及所属测试点是否已删除。省略 `revision_ver` 时返回最新的已冻结修订，没有则报不存在。

## 事件

暂无发出，也暂无订阅。Agent 与用例库的交互方式见 [agent.md](agent.md)。

## 规则

1.  修订的内容产生后不再改动。每条修订保存完整内容，读取任何一条都不依赖其他修订。
2.  实现只能在草稿状态下设置，可以多次覆盖。
3.  冻结要求实现非空。冻结后内容与实现都不可变，冻结不可撤销，对已冻结的修订再次冻结会报错（见 [decisions/002](../decisions/002-implementation-and-freeze.md)）。
4.  任何状态下都可以产生新修订，没有冻结的旧草稿保留，作为历史。
5.  同一测试点并发产生修订时，`(testpoint_id, revision_ver)` 必须唯一，后到者收到冲突错误。
6.  项目版本推进时，内容没有变化的测试点不产生新修订。
7.  测试点被软删除后，已冻结的修订仍然可读，因为旧任务和历史复现依赖它。已删除的测试点不接受任何写入，调用方通过读接口返回的删除标记识别它，并拒绝把它加入新任务。
8.  `actor_id` 只用于记录操作者，各模块只保存这个 id，需要名称时向 Access 读取。
