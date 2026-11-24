# 模块指南

本文说明平台划分为哪些模块、每个模块负责什么、模块之间如何依赖。接口签名和业务规则写在 [modules/](modules/) 下各模块自己的规格里，多个模块共用的形状写在 [contracts/](contracts/)，设计理由记录在 [decisions/](decisions/)。只有模块的划分或依赖关系改变时才需要修改本文。

## 核心概念

| 概念 | 含义 | 归属 |
| --- | --- | --- |
| Project 与 proj_ver | 被测项目及其版本，需求文档和接口文档随版本保存 | Access |
| 测试点 | 从需求和接口文档提炼出的待验证命题，是用例库管理的核心对象 | 用例库 |
| 修订 | 测试点自己的一条线性历史记录，带有实现，经审计后冻结为不可变资产 | 用例库 |
| 任务 | 一次测试要执行的修订清单 | Task |
| 执行结果 | 一次任务执行产生的证据与判定 | 结果系统 |

## 模块

实现状态见 [STATUS_AND_ROADMAP.md](STATUS_AND_ROADMAP.md)，本表不记。

| 模块 | 职责 | 规格 |
| --- | --- | --- |
| Access | 管理用户、项目、项目版本及其文档、项目成员。属于基础支撑，其他模块通过读接口使用它 | [access/](modules/access/) |
| 用例库 | 唯一管理用例树和测试点的修订历史，并决定一条修订何时成为可被引用的正式资产 | [library/](modules/library/) |
| Task | 把已冻结的修订组装成可以启动的任务清单 | [task/](modules/task/) |
| 执行器 | 领取已启动的任务，运行修订的实现，产出执行结果 | [exec/](modules/exec/) |
| 结果系统 | 保存执行结果并提供读取 | [result.md](modules/result.md) |
| Agent | 长流程生成器，经人工审批后向用例库写入。设计待定 | [agent.md](modules/agent.md) |

## 依赖与交互

模块之间有两种交互方式。读取对方已经确定的事实时，通过使用方定义的端口调用对方的读接口，见 [decisions/006](decisions/006-cross-module-read-port.md)；发生了需要对方响应的事情时，发出事件。依赖方向自上而下，没有环。

下表只记有哪些边。读什么、事件里有什么，看依赖方自己的规格和 [contracts/](contracts/)。

| 依赖方 | 被依赖方 | 方式 |
| --- | --- | --- |
| 用例库 | Access | 读接口 |
| Task | 用例库 | 读接口 |
| 执行器 | Task、用例库、Access | 读接口 |
| 执行器 | Task | 订阅 `TaskStarted` |
| 结果系统 | 执行器 | 订阅 `TaskExecCompleted` |
| Agent | 用例库 | 待定 |

这些交互方式背后的理由见 [decisions/005](decisions/005-module-interaction.md)。

## 模块之外的代码

组装根、跨模块适配和共享基础设施不属于任何业务模块：`stsd.bootstrap` 负责组装与 mapper 生命周期，`stsd.integration` 放跨模块端口的实现，`stsd.shared` 放事件发布端口和 [contracts/](contracts/) 里那些跨模块形状。业务模块之间不互相 import。

基础设施没有单独的模块。它以端口加适配器的形式归属于需要它的那个模块——文件存储归用例库，容器运行时归执行器，端口定义在模块自己的 `ports.py`，实现在模块自己的 `adapters/`。只有真正跨模块的才进 `stsd.shared`。
