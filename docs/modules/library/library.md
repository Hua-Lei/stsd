# 用例库模块规格

管理项目内的用例树和测试点的修订历史。本文是对外契约。

## 概念

用例树由两种节点构成：Section 是目录，只负责组织结构；测试点（TestPoint）拥有一条按序号线性增长的修订历史。

修订（TestPointVersion）由 `(testpoint_id, revision_ver)` 标识，`revision_ver` 是测试点自己的序号，从 1 开始。修订包含名称、描述、至多一个实现，以及说明性的 `proj_ver`，后者记录这次修订针对哪个项目版本写成，不参与标识（见 [decisions/001](../../decisions/001-proj-ver-is-descriptive.md)）。修订的状态是草稿或已冻结。

实现的形状不由本模块定义，见 [contracts/implementation-spec.md](../../contracts/implementation-spec.md)。用例库负责校验它的形状、保存它、并保证已冻结修订的实现不可变。

## 对 Access 的依赖

用例库自己定义端口 `ProjectVersionLookup.project_version_exists(project_id, proj_ver)`，只回答"某项目有没有某个 `proj_ver`"。实现是集成层的 `AccessProjectVersionLookup`，包装 Access 的 `get_project_version`；Access 报项目或版本不存在时折叠为 `False`。端口只读不可变事实，必须在用例库写操作之前调用；适配器自持只读事务，不参与用例库事务。见 [decisions/006](../../decisions/006-cross-module-read-port.md)。用例库不直接引用 Access 的对象，只保存 `project_id` 和 `proj_ver` 的值。

## 写操作

以下写操作都返回读模型：创建 Section 返回节点，删除返回被删除节点 id 列表，其余返回修订详情。

*   `CreateSection(actor_id, project_id, parent_id, name)`，父节点必须存在、属于同一项目、未删除且是 Section；`parent_id` 为空表示根下
*   `AddTestPoint(actor_id, project_id, section_id, name, proj_ver)` 同时产生第一条修订，`revision_ver` 为 1，描述和实现为空；`section_id` 校验同上，`proj_ver` 经端口确认存在
*   `DeleteNode(actor_id, node_id)` 软删除该节点及其未删除的后代，返回被删除的节点 id 列表；已删除的节点报错
*   `ReviseTestPoint(actor_id, testpoint_id, proj_ver, revision_detail)` 产生新的修订，实现为空
*   `SetImplementation(actor_id, testpoint_id, revision_ver, implementation)` 整包替换草稿修订的实现，文件、依赖、运行声明一次给全；只能用于草稿，可以反复覆盖
*   `AuditAndFreeze(actor_id, testpoint_id, revision_ver)` 把草稿冻结

实现的编辑做成整包替换而不是逐文件操作：它是一次原子写入，和"实现可以覆盖"这条规则对得上，也不必为增、删、改各自重复一遍同一套草稿校验。界面要做单文件保存时再加细粒度操作，领域模型不受影响。

## 读接口

读接口返回不可变的读模型，字段是模块契约的一部分：新增字段兼容，改名、删除或改变语义是破坏性变更。

*   `get_section_tree(project_id, section_id)` 返回该节点下未删除的直接子节点；`section_id` 省略时返回项目根下的节点，已删除的 Section 返回空列表。Section 节点带 `node_type`、`node_id`、`project_id`、`parent_id`、`name`、`created_at`；测试点节点另带 `latest_revision_ver`、`latest_revision_status`、`latest_frozen_revision_ver`（没有则为空），使界面显示一棵树不必逐个查询详情。
*   `get_testpoint_detail(testpoint_id, revision_ver)` 返回 `testpoint_id`、`project_id`、`revision_ver`、`name`、`description`、`implementation`、`proj_ver`、`status`、`testpoint_deleted`、`created_at`、`created_by`。省略 `revision_ver` 时返回最新的已冻结修订，没有则报不存在；已删除测试点的修订仍然可读。`implementation` 只是声明，不含文件内容。
*   `get_implementation_files(testpoint_id, revision_ver)` 返回包内路径到文件内容的映射，供执行器把文件放进容器。单列一个操作是为了让详情这个读模型保持轻：它被用例树和编辑界面频繁调用，而文件内容只有执行时才需要。

## 事件

暂无发出，也暂无订阅。Agent 与用例库的交互方式见 [agent.md](../agent.md)。

## 错误

所有错误继承 `LibraryError`，具体类型见 `library/domain/errors.py`。

别的模块唯一依赖的区分是：集成层把 Access 的"项目不存在"和"版本不存在"折叠为 `False`，这条折叠是 `ProjectVersionLookup` 端口的契约（见 [decisions/006](../../decisions/006-cross-module-read-port.md)）。

## 规则

1.  修订的内容产生后不再改动。每条修订保存完整内容，读取任何一条都不依赖其他修订。
2.  实现只能在草稿状态下设置，整包替换，可以反复覆盖。
3.  冻结是唯一的闸口，要求实现非空、平台标识已知、`runtime_spec` 指定的 `main_file` 确实在包里、依赖声明合法。冻结之后内容与实现都不可变，冻结不可撤销，再次冻结会报错（见 [decisions/002](../../decisions/002-implementation-and-freeze.md)）。能静态查的都要在这里查完，因为冻结之后没有补救办法。
4.  任何状态下都可以产生新修订，没有冻结的旧草稿保留，作为历史。
5.  同一测试点并发产生修订时，`(testpoint_id, revision_ver)` 必须唯一，后到者收到冲突错误。
6.  内容没有变化的测试点不产生新修订。"内容"指最新修订的名称和描述；未变时 `ReviseTestPoint` 返回最新修订的详情，不产生新修订，也不更新 `proj_ver`。实现的变化不计入，它由 `SetImplementation` 单独管理。
7.  测试点被软删除后，已冻结的修订仍然可读，因为旧任务和历史复现依赖它。已删除的测试点不接受任何写入，调用方通过读接口返回的删除标记识别它，并拒绝把它加入新任务。
8.  `actor_id` 只用于记录操作者，各模块只保存这个 id，需要名称时向 Access 读取。
