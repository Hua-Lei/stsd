# 文档导览

docs/ 按内容的变化速度分层，越靠上的文档越稳定，越靠下的越常改动。新增一条设计信息时，先判断它属于哪一层再落笔。

| 层 | 位置 | 回答的问题 | 变化频率 |
| --- | --- | --- | --- |
| 需求 | [prd.md](prd.md) | 平台要解决什么问题，为什么需要测试点这一层 | 很低 |
| 用户目标 | [use-case-analysis.md](use-case-analysis.md) | 用户用例分析 | 低 |
| 模块划分 | [domain-model.md](domain-model.md) | 有哪些模块，各自负责什么，谁依赖谁 | 低，只在模块边界改变时修改 |
| 模块规格 | [modules/](modules/) | 每个模块的接口、状态规则、错误与读模型契约 | 中，随对业务的理解加深而变化，影响范围限于单个模块 |
| 决策记录 | [decisions/](decisions/) | 某个设计为什么这样定 | 追加新记录，已写的记录不再修改 |
| 当前代码库状态&计划     | [STATUS_AND_ROADMAP.md]([STATUS_AND_ROADMAP.md)                         | 略           | 高                |

模块规格里的 `CreateUser(...)`、`get_user_projects(...)` 是业务操作名，不是 Python 调用形状；操作名与命令对象、服务函数、读模型的对应关系见 [implementation.md](implementation.md) 第 7 节。

判断一条信息该放在哪一层，可以看它改变时会牵动谁。如果修改某个模块的内部规则会迫使你去改模块划分，说明这条信息写在了过高的层次。
