# 平台设计草案

范围：不含测试点与文档的追溯（引用、锚定、影响分析），留到下一期。

## 1. 出发点

平台要做的事：团队借助 AI，针对被测系统建立一套测试资产并长期维护，随时能回答"系统现在是否符合文档"。

由此得出四条约束，后面的设计都从这里推出：

1. **判定交给代码。** 用例是否通过、产出是否合法，由确定性代码判断。LLM 只负责生成和解释。
2. **用例库是唯一的长期状态。** AI 每次工作需要的上下文，都从用例库和文档里现取，不靠积累对话。
3. **写入先审后合。** 人和 AI 的修改都以变更集的形式提交。AI 提交的变更集必须经人批准才生效。
4. **历史不可改。** 修改追加新版本，删除改为废弃。执行结果永远指向它运行时的那个版本。

## 2. 核心对象

| 对象 | 是什么 | 生命周期 |
|---|---|---|
| Project | 一个被测系统，其他对象都挂在它下面 | 长期 |
| Document | 上游文档（需求、OpenAPI）的一个版本 | 只追加新版本 |
| Section | 用例库树上的文件夹（模块、功能） | 版本化 |
| TestPoint | 树的叶子：一个要验证的是非问题 | draft → approved → deprecated，版本化 |
| Implementation | 测试点的可执行实现（现有的 `TestCase`） | 同上 |
| ChangeSet | 对用例库的一批写操作 | proposed → applied / rejected |
| Session | 一次 AI 工作的记录 | running → done / failed |
| Run | 一次执行：一组实现的具体版本，加上执行环境 | pending → running → done / failed |
| Result | Run 中一条实现的执行结果（现有的 `CaseResult`） | 只写一次 |

按变化方式分成三类：

- **资产**（Section、TestPoint、Implementation）：长期维护，版本化。
- **输入**（Document）：由外部给定，只追加。
- **记录**（ChangeSet、Session、Run、Result）：已经发生的事，写入后不再修改。

## 3. 过程模型

### P1 从零建库

前提：只有文档，用例库为空。

```
规划：AI 读文档 → 提出模块和测试点 → 代码校验 → 变更集 → 人工审核 → 合并
实现：对每个通过审核的测试点，AI 生成实现 → 代码校验（不通过就带着错误重试）
      → 变更集 → 人工审核 → 合并
```

人可以在任何一轮加入指令，比如"认证相关的单独成一个模块"。

### P2 增量修改

触发：文档有了新版本，或者有一条人工指令（比如"补充分页的边界测试"）。

```
AI 读：指令或文档差异 + 用例库目录 → 按需展开相关节点
   → 提出新增、修改、废弃 → 代码校验 → 变更集 → 人工审核 → 合并
```

本期没有追溯，影响范围由 AI 判断，靠人工审核把关。

### P3 执行

```
人选一组实现 + 执行环境 → Run 锁定这些实现当前的版本 → 后台执行 → 逐条写入 Result
```

失败的结果可以作为 P2 的输入：AI 读取失败现场，提出修正，形成变更集。

### 共同结构

P1、P2 和修正失败，其实是同一个形态：

```
Session(目标, 可用工具, 校验器, 轮次上限)
   循环：读取状态 → 提出修改 → 校验 → 修正
   产出：一个变更集 → 人工审核 → 合并
```

所以 AI 这一侧只需要一种机制：**带工具、带校验、产出变更集的会话**。

各阶段的先后顺序（先规划、审核，再实现）由代码固定，不交给 AI 决定。

## 4. 需要的功能

从上面的过程模型直接推出：

| 功能 | 被哪个过程用到 |
|---|---|
| 用例库目录视图（只给名称和状态，可以逐层展开） | P1、P2 |
| 节点详情，包括历史版本 | P1、P2、前端 |
| 变更集：提交、校验、批准、拒绝、合并 | 全部 |
| 节点的版本历史 | 审计、前端 |
| 文档版本存储，以及两个版本之间的文本差异 | P1、P2 |
| 产出校验：schema、和接口文档的静态比对 | P1、P2 |
| AI 会话：工具调用循环、记录、轮次上限 | P1、P2 |
| 发起执行、查询状态、按 Run 或按实现查询结果 | P3 |
| 执行环境：base_url、初始变量（鉴权）、超时 | P3 |

## 5. 模块与接口

```
   React 前端                      AI（LLM）
       │ HTTP                        │ tool calls
   API 层 ──────── 工作流：阶段编排、组装会话、工具适配
       │               │              │
   用例库          文档            执行
       └──── 共享模型（demo/models） ────┘
```

依赖规则：

- 用例库、文档、执行三个模块互不依赖。
- 组合它们的逻辑放在工作流和 API 层。
- Agent 运行时不了解测试领域。

### 用例库

```python
class Library:
    def outline(self, project_id, section_id=None, depth=2) -> list[OutlineNode]  # 目录，相当于 ls
    def get(self, node_id, revision=None) -> Node                               # 详情，相当于 cat
    def history(self, node_id) -> list[Revision]
    def propose(self, cs: ChangeSet) -> str      # 校验后存为待审核，返回变更集 id
    def review(self, cs_id, approve: bool, reviewer: str) -> None   # 批准后原子合并
```

变更集的操作类型：新建、修改、移动、废弃。节点 id 稳定不变，路径只用于展示。

### 文档

```python
class Documents:
    def add_version(self, project_id, kind, text) -> DocVersion
    def get(self, project_id, kind, version=None) -> DocVersion
    def diff(self, project_id, kind, v_old, v_new) -> str   # 文本差异，供 P2 使用
```

### 执行

```python
class Runs:
    def start(self, project_id, env: Environment, items: list[RunItem]) -> str  # 立即返回 run_id
    def get(self, run_id) -> Run                         # 状态 + 已完成的结果
    def history(self, implementation_id) -> list[Result]
```

- `RunItem` 由调用方带上用例内容（实现 id、版本、`TestCase`），所以执行模块不读取用例库。
- `Environment` 包含 base_url、初始变量（如鉴权 token）和超时。

### Agent 运行时

```python
def run_session(llm, goal: str, tools: list[Tool], validator, max_rounds) -> Session
# Session 记录：指令、每轮消息、工具调用、产出的变更集、token 用量
```

### 工作流

每个阶段一个函数，决定三件事：给 AI 看哪些上下文、开放哪些工具、用哪个校验器。

```python
def plan(project_id, instruction=None) -> session_id        # P1 规划 / P2 结构调整
def implement(project_id, test_point_ids) -> session_id     # P1 实现
def revise(project_id, instruction, doc_diff=None) -> session_id  # P2
```

### HTTP API

资源都嵌套在 project 下：

```
GET    /projects/{pid}/library?section=&depth=
GET    /projects/{pid}/nodes/{id}?revision=
GET    /projects/{pid}/changesets          POST .../{cid}/review
POST   /projects/{pid}/documents           GET  .../documents/{kind}/diff?from=&to=
POST   /projects/{pid}/sessions            GET  .../sessions/{sid}
POST   /projects/{pid}/runs                GET  .../runs/{rid}
```

会话和执行都是长时间任务：POST 立即返回 id，前端轮询状态。

## 6. 关键设计决策

| 决策 | 理由 |
|---|---|
| 阶段顺序由代码固定，阶段内部交给 AI 循环 | 人工关卡不能被跳过，结果能复现，成本可控 |
| AI 只能读取状态和提交变更集，不能直接修改用例库 | AI 出错时，最坏的结果是一个被拒绝的草稿 |
| 人在界面上的修改也走变更集，作者记为"人" | 只有一套写入路径，历史记录是统一的 |
| AI 的上下文先给目录，需要时再展开节点 | 用例库会越来越大，不能每次都整个塞给 AI |
| 修改追加新版本，删除标记为废弃 | 执行结果和审核记录始终能对应回原来的版本 |
| Result 附带执行时用例内容的快照 | 用例以后被修改，历史结果仍然可以解读 |
| 服务端无状态，每个请求都带 project_id | 支持多标签页、多用户，服务重启后状态不丢 |
| 前端和 AI 是同一组服务的两个客户端 | 校验规则和业务规则只写一份 |

## 7. 本期不做

- 测试点与文档的追溯：引用、锚定、影响分析、覆盖缺口。
- 基线和标签、两个版本之间的比较、多条发布线。
- AI 对失败结果的归因分析（判断是产品缺陷、用例问题还是环境问题）。
- 登录和权限。本期 API 没有任何鉴权，只能在可信网络里使用，不能暴露到公网。
