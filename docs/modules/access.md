# Access 模块规格

负责用户、项目、项目版本及其文档、项目成员。没有复杂的业务流转，其他模块只通过它的读接口使用它。

## 写操作

*   `CreateUser(actor_id, user_info)`
*   `CreateProject(actor_id, project_name, web_config)`
*   `AddProjectVersion(actor_id, project_id, proj_ver, docs)`，其中 `docs` 是文档列表，每份文档包含类型 `kind`（`requirements` 表示需求文档，`openapi` 表示接口文档）和原文 `text`
*   `AddUserToProject(actor_id, project_id, target_user_id)`

## 读接口

*   `get_user_projects(user_id)`
*   `get_project_members(project_id)`
*   `list_project_versions(project_id)` 列出项目的所有版本，供界面选择
*   `get_project_version(project_id, proj_ver)` 返回该版本及其全部文档，版本不存在时报不存在

## 事件

暂无发出，也暂无订阅。

## 规则

1.  项目版本添加后不可修改，也不可删除，其文档在添加时一次性提供。
2.  同一项目内 `proj_ver` 唯一，重复添加报错。
3.  用例库确认项目版本是否存在时，由 `get_project_version` 提供答案。
4.  `actor_id` 只用于记录操作者，不做成员或权限校验，见 [decisions/003](../decisions/003-actor-id-provenance.md)。
