# 执行器模块规格

> 状态：已实现（同步执行）；任务事件尚未接入。

执行计划中的测试点，运行它们的实现，产出步骤级证据与用例级判定。不关心任务和用例是怎么建立的，也不保存结果。

## 写操作

*   `Execute(plan)` 按顺序执行计划中的全部测试点，返回 `ExecutionOutcome`。
*   单条测试点执行没有独立操作：构造只含一条 `ExecutionTestPoint` 的 `ExecutionPlan`，调用同一个 `Execute(plan)`。

## 读依赖

无。执行器不读取任务清单或用例库；执行内容由调用方组装成计划后传入。

## 输入契约

*   `ExecutionPlan`：有序的 `ExecutionTestPoint` 加一个 `Environment`。
*   `ExecutionTestPoint`：`seq`、`testpoint_id`、`revision_ver`、`content_hash`、`payload`。执行器原样带出这些标识，不重新解析修订。
*   `Environment`：`base_url`、`headers`、`variables`、`timeout_seconds`；后两者由 Workflow 或调用方传入。
*   `payload` 必须能通过 `TestCase` 校验：`id`、`title`、`category`、`steps`；至少一个步骤；未声明字段报错。
*   `Step`：`name`、`request`、`extract`、`assertions`。
*   `Request`：`method` 只能是 `GET`、`POST`、`PUT`、`PATCH`、`DELETE`；`path`、`headers`、`query`、`body` 可包含 `{{变量}}`。
*   `Assertion`：`source` 为 `status`、`body` 或 `header`；`op` 为 `eq`、`ne`、`in`、`exists`、`not_exists`、`contains`、`gt`、`lt`；`path`、`expected`。
*   `extract` 的键必须是合法变量名，值是 JSONPath；目前只支持 `$`、`.key`、`[index]`。

## 执行

1.  校验 payload；不合法时该测试点记为 `error`，`error_type=invalid_case`，不产生步骤。
2.  复制环境变量，作为本条用例的变量表。
3.  按 `steps` 顺序执行；前一步不是 `passed` 时，当前步骤记为 `skipped`，不发送请求。
4.  步骤内依次：绑定变量、合并环境 headers（用例可覆盖）、拼接 URL、发请求、求值断言、提取变量。
5.  断言全部通过后才提取变量；提取失败记为 `extract_error`。
6.  用例状态归并：任一步骤 `error` → `error`；否则任一步骤 `failed` → `failed`；否则 `passed`。

## 输出

*   `ExecutionOutcome`：`status=completed`、`started_at`、`finished_at`、`testpoints`。
*   `TestPointOutcome`：`seq`、`testpoint_id`、`revision_ver`、`content_hash`、`title`、`status`、`error_type`、`message`、`steps`、`duration_ms`、起止时间。
*   `StepOutcome`：`index`、`name`、`status`、`error_type`、`message`、请求快照、响应快照、断言记录、`extracted`、`duration_ms`。
*   步骤级允许 `skipped`；用例级只有 `passed`、`failed`、`error`。

## 事件

暂无发出，也暂无订阅。目标设计中的 `TaskStarted` / `TaskExecCompleted` 尚未接入，当前由 Workflow 同步调用。

## 错误

执行器不抛业务错误，失败通过状态与 `error_type` 表达：

*   `invalid_case` payload 无法通过 `TestCase` 校验，用例直接记为 `error`
*   `assertion_failed` 请求成功，至少一条断言不通过
*   `render_error` 模板引用了不存在的变量
*   `timeout` 请求超时
*   `transport_error` 连接失败、DNS 失败等 HTTP 传输错误
*   `extract_error` 断言通过后按 JSONPath 提取失败
*   `executor_error` 执行器兜底异常

用例的 `error_type` 和 `message` 取首个失败或错误步骤；断言失败不是异常。

## 规则

1.  测试点按计划顺序执行，条目顺序就是执行顺序。
2.  单条测试点失败或异常不影响其他测试点。
3.  步骤快速失败：前一步不是 `passed`，后续步骤记为 `skipped`，不发送请求。
4.  用例状态优先级：任一步骤 `error` → 用例 `error`；否则任一步骤 `failed` → 用例 `failed`；否则 `passed`。
5.  变量在一条用例内共享；提取变量只在该步骤断言通过后生效。
6.  整个字符串恰好是占位符时保留变量原类型，嵌在文本中时转成字符串拼接；变量缺失是执行错误。
7.  环境 headers 先合并，用例 headers 可以覆盖同名头。
8.  `base_url` 可以带路径前缀，`path` 可以带前导斜杠。
9.  断言只做确定性比较，不做类型转换；字段不存在与 JSON `null` 是两种结果。
10. `exists` / `not_exists` 只判断字段是否存在；其余 op 在字段缺失时一律判失败。
11. `contains` 对字符串是子串、对列表是元素、对字典是 key。
12. 执行器不读数据库、任务清单或用例库，也不把结果写入任何存储。
13. 单条测试点的失败不把整批 `ExecutionOutcome` 标成 `aborted`，它仍是 `completed` 中的一条结果。
14. 目标设计中的 `ExecTestCaseForTest` 尚未独立实现；单条执行由“单条测试点的计划”表达。

实现位置：`stsd/executor/`。调用入口：`CaseExecutor(client).execute(plan)`；在平台内由 `HttpExecutorAdapter` 适配成 `ExecutorPort`。
