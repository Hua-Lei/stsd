# Access 模块规格

负责用户、项目、项目版本及其文档、项目成员。没有复杂的业务流转，其他模块只通过它的读接口使用它。

## 写操作

*   `CreateUser(actor_id, user_info)`，`user_info` 包含非空的 `name` 和可选的 `email`
*   `CreateProject(actor_id, project_name, web_config)`，`web_config` 必须是可 JSON 序列化的对象
*   `AddProjectVersion(actor_id, project_id, proj_ver, docs)`，`docs` 是文档列表，每份文档包含类型 `kind`（`requirements` 表示需求文档，`openapi` 表示接口文档）和非空原文 `text`；可以为空列表
*   `AddUserToProject(actor_id, project_id, target_user_id)`，重复添加按幂等处理，返回已有的成员关系

## 读接口

读接口返回不可变的读模型，字段是模块契约的一部分：新增字段兼容，改名、删除或改变语义是破坏性变更。

*   `get_user_projects(user_id)` 返回 `ProjectView` 列表，字段为 `project_id`、`name`、`web_config`、`created_at`
*   `get_project(project_id)` 返回单个 `ProjectView`，字段同上；项目不存在时报不存在
*   `get_project_members(project_id)` 返回 `ProjectMemberView` 列表，字段为 `project_id`、`user_id`、`name`、`email`、`added_by`、`added_at`
*   `list_project_versions(project_id)` 返回按创建时间排序的 `proj_ver` 字符串列表
*   `get_project_version(project_id, proj_ver)` 返回 `ProjectVersionView`，字段为 `project_id`、`proj_ver`、`docs`、`created_at`，每份文档带 `kind` 和 `text`；版本不存在时报不存在

## 事件

暂无发出，也暂无订阅。

## 错误

所有错误继承 `AccessError` 并带稳定 `code`，入口层捕获基类后按 `code` 映射响应：

*   `InvalidArgument`（`INVALID_ARGUMENT`）入参形状或取值不合法
*   `UserNotFound`（`USER_NOT_FOUND`）用户不存在
*   `ProjectNotFound`（`PROJECT_NOT_FOUND`）项目不存在
*   `ProjectVersionNotFound`（`PROJECT_VERSION_NOT_FOUND`）项目版本不存在
*   `DuplicateProjectVersion`（`DUPLICATE_PROJECT_VERSION`）同一项目内版本重复

## 规则

1.  项目版本添加后不可修改，也不可删除，其文档在添加时一次性提供。
2.  同一项目内 `proj_ver` 唯一，重复添加报错；并发添加由唯一约束兜底。
3.  用例库确认项目版本是否存在时，通过 `ProjectVersionLookup` 端口调用 `get_project_version`；错误折叠与事务纪律见 [decisions/006](../decisions/006-cross-module-read-port.md)。
4.  创建项目不会自动把创建者加入项目成员，成员关系只由 `AddUserToProject` 建立。
5.  `actor_id` 只用于记录操作者，不做成员或权限校验，见 [decisions/003](../decisions/003-actor-id-provenance.md)。
