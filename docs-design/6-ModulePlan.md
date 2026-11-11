# 模块划分与初期分工

## 目标

平台的核心资产是每个项目的用例库，组织成"模块 → 测试点 → 实现"的树。

- 上游文档进来后，AI 先从文档提取测试点，人工审核。
- 测试点通过审核后，AI 生成可执行的实现，再经人工审核。
- 执行器运行实现，结果记录进执行历史。
- 每个测试点都记录它引用了文档里的哪些原文。文档更新时，通过检查这些引用是否仍然成立，找出受影响的测试点。

两条贯穿始终的原则：

1. LLM 只负责生成和解释。通过与否、引用是否成立，由确定性代码判定。
2. AI 的写入一律先形成待审核的变更集，经人确认后才进入用例库。

这一期的目标是：各模块先实现最基本的功能，接口跑通。每个模块配有单元测试，能单独演示。

## 模块总览

```
   React 前端                Agent 运行时（通用，不懂测试领域）
       │ HTTP                     │ tool calls
   API 层 ───────── 生成工作流（阶段编排、人工关卡、工具适配）
       │                │                 │
   用例库          文档与追溯          执行与历史
       └────────── 共享契约（demo/models） ──────────┘
```

| 编号 | 工作包 | 目录 | 依赖 | 能否立即开始 |
|---|---|---|---|---|
| WP0 | 共享契约 | `demo/models/` | 无 | 是，先做，1 到 2 天 |
| WP1 | 用例库 | `demo/library/` | WP0 | WP0 定稿后 |
| WP2 | 文档与追溯 | `demo/tracing/` | WP0 中的 Citation | 是 |
| WP3 | LLM 与 Agent 运行时 | `demo/agent/` | 无 | 是 |
| WP4 | 执行与历史 | `demo/runs/` | WP0，现有执行器 | WP0 定稿后 |
| WP5 | 生成工作流 | `demo/workflow/` | WP1、WP2、WP3 的接口 | 先做原型，接口稳定后再接入 |
| WP6 | API 与前端 | `demo/api/`、`web/` | 各模块接口 | 先用假数据做前端 |

## 共同约定

- **契约先行。** 模块之间传递的对象定义在 `demo/models/` 里（pydantic）。改契约要先在群里说明，因为它会影响所有人。
- **依赖方向。** 用例库、文档与追溯、执行与历史这三个领域模块互不 import，只依赖 `demo/models`。需要把它们组合起来的逻辑，写在生成工作流或 API 层。Agent 运行时不依赖任何领域模块。
- **对外接口。** 每个模块只把 `__init__.py` 里导出的内容当作公开接口，其他模块不要 import 它的内部文件。
- **存储。** 全部共用一个 SQLite 文件，连接从外部注入，参考 `demo/persistence/db.py` 的 `connect`。每个模块只管理自己的表。
- **导入。** 一律使用绝对导入，例如 `from demo.models import ...`。
- **测试。** 用标准库 unittest，放在 `tests/` 下，运行命令是 `.venv/bin/python -m unittest discover -s tests -t . -v`。单元测试不能调用真实的 LLM，也不能访问网络。
- **LLM 配置。** 走环境变量 `DEEPSEEK_API_KEY` 等，参考 `demo/generator/config.py`。
- **测试素材。** 统一使用 `experiments/testpoint_ab/fixtures/`。里面有被测服务 `target_app.py`（学习者 CRUD，埋了 5 个可开关的缺陷），以及接口文档 `openapi.json` 和需求文档 `requirements.md`。

## 现有代码

| 位置 | 状态 | 处理方式 |
|---|---|---|
| `demo/models/case.py`、`result.py` | 稳定 | `TestCase` 继续作为"实现"的内容格式，`CaseResult` 继续作为执行结果的格式 |
| `demo/executor/` | 可用 | 由 WP4 在外面再包一层 |
| `demo/generator/` | 可用，属于"直接生成用例"的朴素版 | 其中的提示词和校验逻辑由 WP5 吸收 |
| `demo/persistence/case_repo.py` | 扁平的用例表 | 被 WP1 取代，`db.py` 保留 |
| `experiments/` | 两组 A/B 实验的脚本和结果 | 供 WP5 参考 |

## WP0 共享契约

目标：把模块之间传递的核心对象先定下来，让其他工作包可以并行开工。字段只放这一期必须的，后续按需增加。

```python
class Section:          # 树上的文件夹（模块/功能划分）
    id: str; project_id: str; parent_id: str | None; name: str

class Citation:         # 测试点的依据：文档原文的逐字引文
    doc_id: str
    quote: str          # 逐字原文
    prefix: str         # 引文前的一小段上下文，用于重新锚定
    suffix: str         # 引文后的一小段上下文
    verified_version: int   # 最后一次确认成立的文档版本

class TestPoint:        # 树的叶子：一个要验证的是非问题
    id: str; section_id: str; title: str
    rationale: str      # 为什么从这些引文推出这个测试点
    citations: list[Citation]
    status: Literal["draft", "approved", "deprecated"]
    revision: int

class Implementation:   # 测试点的实现，一个测试点可以有多个
    id: str; test_point_id: str
    content: TestCase   # 沿用现有模型
    status: Literal["draft", "approved", "deprecated"]
    revision: int

class DocSnapshot:      # 上游文档的一个版本
    doc_id: str; version: int; kind: Literal["requirements", "openapi"]; text: str

class ChangeSet:        # 一批写操作，原子生效
    id: str; author: str          # 人的用户名，或者 "agent:<session_id>"
    ops: list[Op]
    status: Literal["proposed", "applied", "rejected"]
```

约定：

- 节点的 id 是稳定的，路径只用于展示。
- 每次修改，`revision` 加 1。
- 执行结果引用的是"实现 id + revision"。

验收：模型能 JSON 序列化后再还原，写入和读回的结果一致；WP1 到 WP4 的负责人确认这些字段够用。

## WP1 用例库

目标：负责项目用例资产的持久化、查询和版本历史。对外表现为一棵可以浏览的树。

本期范围：

- 文件夹、测试点、实现的增删改查。所有写操作都通过 `apply(changeset)` 完成：一个变更集里的操作，要么全部生效，要么全部不生效。
- 操作类型有新建、修改、移动、废弃。
  - 修改不覆盖原内容，而是追加一个新的修订版本。
  - 删除改为标记"废弃"，因为执行历史还会引用旧的修订版本。
- 移动节点只改变它的父节点，不改变 id。

接口草案：

```python
class Library:
    def apply(self, cs: ChangeSet) -> None: ...
    def outline(self, project_id: str, section_id: str | None = None, depth: int = 2) -> list[OutlineNode]: ...
    def get(self, node_id: str, revision: int | None = None) -> Section | TestPoint | Implementation | None: ...
    def history(self, node_id: str) -> list[Revision]: ...
```

`outline` 只返回名称、状态和子节点数量，相当于 `ls`。`get` 返回完整内容，相当于 `cat`。

本期不做：基线和标签、两个版本之间的 diff、多人同时编辑时的冲突处理。

验收：

- 一个变更集里只要有一个操作不合法（比如父节点不存在），整批都不会生效。
- 修改之后，新旧两个修订版本都能读到。
- 节点移动后 id 不变，`get` 仍然能取到。
- 废弃的节点默认不出现在 `outline` 里。

## WP2 文档与追溯

目标：文档更新后，判断测试点引用的原文还成不成立。这是整个追溯机制的核心。它由纯函数组成，不依赖其他模块，可以第一个开工。

思路：文档没有稳定的结构，所以不对文档做 diff，而是逐条检查每个引用在新文档里能不能找到。这和 W3C Web Annotation 里的 TextQuoteSelector 是同一个思路：引文本身加上前后文，再做模糊匹配。

本期范围：

- 存储文档快照：保存全文和版本号，不要求文档有结构。
- 引文校验：LLM 给出的引文，必须是文档里真实存在的逐字片段。
- 重新锚定：拿旧引用到新文档里查找，结果分三类：
  - `exact`：原文精确找到，自动绑定到新版本。
  - `fuzzy`：措辞小改，或者位置变了，需要再确认。
  - `lost`：原文被修改或删除，对应的测试点受影响。
- 覆盖缺口：新文档里没有被任何引用锚定到的段落。

接口草案：

```python
def make_citation(doc: DocSnapshot, quote: str) -> Citation   # 引文不在文档中则抛错
def reanchor(c: Citation, new_doc: DocSnapshot) -> AnchorResult  # exact / fuzzy / lost，附匹配位置和相似度
def uncovered(doc: DocSnapshot, citations: list[Citation]) -> list[Span]
```

验收：基于 `fixtures/requirements.md` 手动改出一版新文档，然后检查下面四种情况。

| 改动 | 期望结果 |
|---|---|
| REQ-002 的长度上限 50 改为 100 | 引用这句话的 Citation 为 `lost` |
| 改写 REQ-003 的措辞，但含义不变 | `fuzzy` |
| 新增一条 REQ-007 | 出现在 `uncovered` 里 |
| 新增一句全局规则，比如"所有名称上限改为 100" | 预期锚定发现不了。把结果记下来，作为以后加 AI 兜底粗筛的依据 |

模糊匹配用什么算法、阈值取多少，由负责人选定，并把理由写下来。OpenAPI 这类结构化文档本期先不处理。

## WP3 LLM 与 Agent 运行时

目标：做一个通用的 agent 运行时，它不了解测试领域，领域知识全部通过工具注入进来。

本期范围：

- **LLM 网关。** 统一的调用入口，支持 tool calling（OpenAI 兼容协议），记录 token 用量，失败时重试。要先确认我们用的 DeepSeek 模型支持 tool calling。
- **工具定义。** 每个工具包含名称、描述、参数的 JSON Schema 和处理函数。
- **Agent 循环。** 调用 LLM，执行它请求的工具，把结果交回给它，如此往复，直到它给出最终回答，或者达到轮次上限。
- **会话记录。** 记下指令、每一轮的消息、工具调用和结果、token 用量。

接口草案：

```python
class LLM(Protocol):
    def chat(self, messages: list[dict], tools: list[Tool]) -> LLMReply: ...   # 回答文本或工具调用，带 usage

@dataclass
class Tool:
    name: str; description: str; parameters: dict; handler: Callable[[dict], Any]

def run_agent(llm: LLM, system: str, instruction: str, tools: list[Tool], max_rounds: int = 10) -> Session: ...
```

验收：

- 用一个按脚本回复的假 LLM 做单元测试，验证三件事：
  - 工具被正确调用，结果被交回给 LLM。
  - 达到轮次上限时停止。
  - 会话记录完整。
- 另外写一个调用真实 LLM 的冒烟脚本，不放进单元测试：让 agent 用一个"查询天气"的假工具回答问题。

## WP4 执行与历史

目标：把一组实现交给执行器运行，记录每一次执行，并且之后能查询。

本期范围：

- **Environment（执行环境）。** 包含 base_url、初始变量（用来放鉴权 token 之类）和单个请求的超时。
  - 需要给 `CaseExecutor` 增加"注入初始变量"的能力。现在每条用例都从空的变量表开始。
- **Run（一次执行）。** 引用一组"实现 id + revision"。
  - 状态依次为 `pending → running → succeeded / failed`。
  - 在后台线程里执行，可以轮询它的状态。
- **结果入库。** 每条 `CaseResult` 入库时，附带当时用例内容的快照。之后用例被修改，历史结果也还能对应上执行时的内容。
- **查询。** 支持按 Run 查询全部结果，也支持查询某个实现的执行历史。
- **顺带清理。** `demo/executor/assert.py` 用关键字做文件名，没法 import，而且和 `assertions.py` 重复。`demo/exec-test.py` 的用途也需要确认。

接口草案：

```python
class RunService:
    def start(self, project_id: str, env: Environment, items: list[RunItem]) -> str: ...   # 返回 run_id，立即返回
    def get(self, run_id: str) -> Run: ...              # 状态 + 已完成的结果
    def history(self, implementation_id: str) -> list[CaseResultRecord]: ...
```

`RunItem` 由调用方带上用例内容（`implementation_id`、`revision`、`TestCase`）。执行模块不去读用例库，所以它不依赖 WP1。

验收：

- 用 `create_app()` 起一个进程内的被测服务，用 TestClient 注入，可以参考 `experiments/testpoint_ab/run.py` 里 `TestClient(create_app(bugs))` 的做法。
- 跑完 fixtures 里的用例后，Run 的状态从 pending 变为 succeeded。
- 结果和用例快照能查询到。
- 开启某个缺陷后，对应的用例变为 failed。

## WP5 生成工作流

目标：把"文档 → 测试点 → 实现"这条流程串起来。依赖 WP1 到 WP3 的接口，所以先做原型，等接口稳定后再接入。

阶段由代码推进，不交给 agent 自行决定：

1. **规划。** 划分模块，提取测试点，每个测试点附上引文和理由。
2. **人工审核测试点。**
3. **实现。** 为通过审核的测试点生成 `TestCase`。
4. **校验与修正。** 校验包括三项：schema 校验、引文校验（WP2）、和接口文档的静态比对（现有的 `static_warnings`）。不通过的，把错误反馈给 agent 修改，设轮次上限。
5. **人工审核实现。**

每个阶段是一次 agent 会话，只开放这个阶段需要的工具，比如用例库的只读视图，以及"提交变更集"。agent 的产出一律是待审核的变更集。

现有素材：

- `demo/generator/` 里的提示词和校验逻辑。
- `experiments/testpoint_ab/run.py` 里"先测试点、再实现"的那一组实验，可以直接作为原型的起点。

实验结论要注意。下面是 LangBase 上的 2×2 实验，9 个埋入缺陷，每组生成 20 条用例，重复 3 次：

| 组 | 检出缺陷数 | 误报数 | 平均 tokens |
|---|---|---|---|
| A1 直接生成 + 设计规则 | 3 / 3 / 5 | 2 / 7 / 2 | 约 3.1 万 |
| B1 测试点（带规则）→ 实现 | 8 / 6 / 7 | 6 / 9 / 9 | 约 28 万 |

测试点这一层提高了检出率，但误报也更多，成本大约是 9 倍。怎么控制误报，是这个工作包要继续探索的问题。

验收：

- 在 fixtures 文档上跑通一次完整流程，产出待审核的测试点变更集，所有引文都通过 WP2 的校验。
- 审核通过后，生成的实现能交给 WP4 执行。

## WP6 API 与前端

目标：让人能浏览用例库、审核变更集、发起执行、查看结果。API 层很薄，只做参数校验和转发。前端只调用 API。

本期范围：

- **API（FastAPI）。** 资源按 project 嵌套组织：
  - `/projects/{pid}/library/...`：树视图、节点详情
  - `/projects/{pid}/changesets`：列表、详情、批准或拒绝
  - `/projects/{pid}/runs`：发起执行、轮询状态
  - 生成和执行都是长时间任务：POST 立即返回任务 id，前端轮询。
- **前端（Vite + React + TypeScript）。** 使用 TanStack Query 和 Ant Design。页面包括：
  - 用例库树
  - 测试点详情：引文、理由、实现列表
  - 变更集审核页：这是人工关卡所在的页面
  - 执行结果页
- **TypeScript 类型。** 由 FastAPI 生成的 `openapi.json` 自动生成，不手写。

在其他模块完成之前，前端先用假数据开发，API 先返回固定的示例数据，联调阶段再接入真实模块。

验收：在浏览器里能完成这条流程：浏览树 → 打开测试点 → 批准一个变更集 → 发起执行 → 看到结果。

## 节奏与里程碑

| 阶段 | 内容 |
|---|---|
| 阶段 0 | WP0 定稿。WP2、WP3 不依赖它，同时开工 |
| 阶段 1 | WP1、WP4、WP6 并行开发，各自用假数据或 fixtures 测试 |
| 阶段 2 | WP5 接入 WP1 到 WP3，WP6 接入真实 API |

**里程碑 M1（端到端）：** 导入 fixtures 里的两份文档，然后依次完成：

1. AI 生成测试点
2. 审核
3. AI 生成实现
4. 审核
5. 对 `target_app.py` 执行
6. 在界面上看到结果

**里程碑 M2（增量）：** 修改需求文档后，系统标出受影响的测试点和覆盖缺口。

## 分工

| 工作包 | 负责人 | 备注 |
|---|---|---|
| WP0 共享契约 | | 建议由项目负责人来做 |
| WP1 用例库 | | |
| WP2 文档与追溯 | | 偏算法，适合喜欢做实验的人 |
| WP3 LLM 与 Agent 运行时 | | |
| WP4 执行与历史 | | 和现有执行器关系最紧 |
| WP5 生成工作流 | | 最需要理解整体设计，建议由负责人或资深成员来做 |
| WP6 API 与前端 | | 可以拆成后端和前端两个人 |

## 待负责人决策

- **Agent 的自主程度。** 默认方案是外层由平台固定阶段，阶段内由 agent 循环。
- **模块树由谁维护。** 默认方案是第一次由 AI 提取，之后归人工维护；文档变化时，AI 只建议新的测试点挂在哪个模块下。
- **生成策略和误报控制。** 根据 WP5 的实验数据来定。
