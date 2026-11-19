# 实现约定

本文说明 `docs/` 的契约在 `src/` 里如何落地。它是文档里最不稳定的一层：代码改动时同步本文；与代码冲突时以代码为准，并在同一次改动里修正本文。业务规则和接口语义不在这里重复，见 [modules/](modules/) 与 [decisions/](decisions/)。

## 1. 代码地图

| 位置 | 职责 |
| --- | --- |
| `stsd.access/`、`stsd.library/` | 两个已实现的业务模块 |
| `stsd/<module>/domain/` | 聚合、值对象、领域错误；不依赖框架 |
| `stsd/<module>/adapters/` | ORM 映射与仓储；只负责持久化，不提交事务 |
| `stsd/<module>/service_layer/` | 服务函数、读模型（`views.py`）、工作单元 |
| `stsd/<module>/command.py` | 命令与读请求对象 |
| `stsd/<module>/ports.py` | 模块依赖的外部端口，只有需要依赖其他模块时才存在 |
| `stsd/<module>/app.py` | 模块的装配入口：把服务函数、工作单元、端口绑成 `*App` |
| `stsd/<module>/__init__.py` | 模块门面，唯一的对外 import 点 |
| `stsd.bootstrap` | 组装根：mapper 生命周期、跨模块依赖选择、组装 `AppContext` |
| `stsd.integration` | 跨模块适配：把对方门面的公开接口适配成本模块的端口 |
| `stsd.shared` | 跨模块基础设施，目前只有事件发布端口和进程内总线 |
| `stsd.config` | 数据库连接配置 |
| `stsd.tasklist` | 旧任务清单设计草稿，未接入装配，状态见第 8 节 |

## 2. 模块公开面

调用方只能 import 模块包顶层 `__init__.py` 导出的名字。门面导出命令与读请求对象、服务函数、读模型、错误类型、`AbstractUnitOfWork`、装配入口 `build_*_app` 和 `*App`，以及命令会用到的值对象（`Document`、`UserInfo`、`RevisionDetail` 等）。聚合、实体、ORM 映射、仓储和会话工厂不得出现在门面上。

例外只有两处：`stsd.bootstrap` 可以 import 各模块的 `adapters.orm` 来启停 mapper；`stsd.integration` 可以同时 import 提供方和使用方的门面。模块之间不得从对方的内部路径 import。

## 3. 用例调用约定

模块门面是给模块内测试和组合使用的：写操作为 `create_user(uow, command)`，需要外部端口的为 `add_testpoint(uow, dep, command)`。调用方提供 UoW，服务函数内部 `with uow` 并显式 `commit()`；不要在外面把同一个 UoW 再包一层 `with`，那会二次进入并替换会话。

应用入口是给外层使用的：`AppContext.access.create_user(command)`、`AppContext.library.add_testpoint(command)`。工作单元在 `app.py` 的绑定函数里每次新建，调用方看不到。一个用例一个事务，跨模块调用不共享事务。

命令对象是 frozen dataclass，只放本次调用的业务字段，不放仓储、会话等工作单元相关对象。校验分三层：值对象在构造期校验（`UserInfo`、`Document`、`RevisionDetail`），服务层校验标量参数和引用完整性，聚合方法校验领域不变量。

## 4. 读模型与错误契约

读接口和写用例都返回 `views.py` 里的 frozen 读模型，不返回聚合或实体：投影在事务内完成，会话关闭后调用方仍可使用。读模型字段是模块契约的一部分，新增字段兼容，改名、删除或改变语义是破坏性变更。

错误类型统一继承模块错误基类并带稳定 `code`，入口层捕获基类后按 `code` 映射响应，不需要认识每个子类。两个模块存在同名错误（`InvalidArgument`、`ProjectVersionNotFound`），按模块基类区分。

## 5. 跨模块读依赖

使用方在 `ports.py` 定义 Protocol，只表达自己需要回答的问题，不复制对方模型；实现放在 `stsd.integration.<provider>`，由组装根注入。见 [decisions/006](decisions/006-cross-module-read-port.md)。

端口的使用纪律是：只读不可变事实；必须在写操作之前调用；适配器自持事务，不参与调用方事务；错误折叠规则属于适配器契约。当前唯一的端口是 `ProjectVersionLookup`，由 `AccessProjectVersionLookup` 包装 Access 的 `get_project_version`。存在性检查会读出整个版本和文档，是已知代价；批量场景成为瓶颈时先在 Access 增加轻量查询。

## 6. 组装与事件

`bootstrap()` 依次执行：启动 mapper；构建 `AccessApp`；选择 `ProjectVersionLookup`（默认用集成层适配器，测试可注入内存实现）；构建 `LibraryApp`；返回 `AppContext`。`AppContext` 不暴露 UoW、会话和适配器，只暴露发布者和两个模块的入口。

工作单元在 `commit()` 成功之后发布聚合记录的事件。当前两个模块都没有事件，也没有订阅者，因此组装根没有订阅表。出现事件时，由模块提供注册入口，在 `bootstrap()` 里调用；跨模块事件通过 `EventPublisher` 端口分发，进程内实现是 `MessageBus`，外部 broker 将来作为同一端口的另一种适配器加入。不引入命令总线和模块内部事件总线。

## 7. 文档与代码的对应

模块规格里的操作名（如 `CreateUser`、`get_user_projects`）是业务操作名，不是 Python 签名。代码里的对应关系是：`command.py` 的请求对象用 PascalCase 同名（`CreateUser`、`GetUserProjects`），`service_layer/service.py` 的服务函数用 snake_case（`create_user`、`get_user_projects`），读接口的返回类型在 `service_layer/views.py`。字段和调用形状以代码为准，模块规格只描述语义和读模型字段契约。

## 8. 已知偏差

Task、执行器、结果系统、Agent 尚未实现，[modules/](modules/) 中它们的规格是目标设计；`stsd.tasklist` 是旧设计草稿（`use_case_version`、`release_order`、`content_hash`），未接入 `bootstrap`，与 [modules/task.md](modules/task.md) 冲突，待团队定性后废弃或重写。

`create_section` 不校验 `project_id` 在 Access 是否存在，只校验父节点，因此可以造出孤立节点，这一点待定。模块门面仍导出具体 `SqlAlchemyUnitOfWork` 供模块内测试和装配使用，跨模块调用方不应用它构造对方的 UoW。
