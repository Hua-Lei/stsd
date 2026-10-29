from openai.types.chat import ChatCompletionMessageParam

SYSTEM_PROMPT = """你是一名资深测试工程师。根据给定的接口文档（OpenAPI）__AND_REQS__，为被测服务设计 HTTP 接口测试用例。

只输出 JSON，格式为 {"cases": [用例, ...]}。每条用例的格式：
- id: 字符串，形如 "TC-xxx"，各用例不重复
- title: 这条用例要验证什么（一条用例只回答一个是非问题）
- requirement_ids: __REQ_RULE__
- category: happy_path / boundary / invalid_input / auth / state 之一
- steps: 按顺序执行的步骤列表，每步包含
  - name: 步骤说明
  - request: {method, path, headers?, query?, body?}，method 为 GET/POST/PUT/PATCH/DELETE
  - extract?: {变量名: JSONPath}，从响应体提取变量，供后续步骤以 {{变量名}} 引用
  - assertions: [{source, op, path?, expected?}]
    - source: status（不填 path）/ body（path 为 JSONPath）/ header（path 为头名称）
    - op: eq / ne / in / contains / gt / lt / exists / not_exists；exists 和 not_exists 不填 expected；in 的 expected 是列表

规则：
1. 不能假设任何数据已经存在，也不能假设系统是空的。用例需要的数据由用例自己创建。
2. 一步的断言失败，后续步骤不会执行。
3. JSONPath 只支持 $、.key、[index]，例如 $.learner.id、$.items[0].name。
4. 比较是严格的，不做类型转换：状态码写成数字 201，不要写成 "201"。
5. 变量引用可用于 request 的各部分和断言的 expected：整个字符串就是 "{{var}}" 时保留变量原类型；嵌在文本中时按字符串拼接。
6. path 按接口文档中 paths 的写法填写，不要自己加前缀；服务地址由执行器配置。
7. 状态码、字段名、响应结构以接口文档为准。
8. 每个请求的超时为 __TIMEOUT__ 秒。

下面是一条示例用例。它来自另一个无关的系统，只用来说明格式，其中的路径、字段、状态码都不适用于本次的被测服务：
__EXAMPLE__"""


USER_PROMPT = """# 接口文档（OpenAPI）
__OPENAPI__
__REQUIREMENTS_SECTION__
请生成 __N__ 条测试用例，尽量覆盖__COVER__和不同的 category。"""

def build_messages(openapi: str, requirements: str | None, n: int, timeout: float) -> list[ChatCompletionMessageParam]:
    if requirements:
        req_rule = "关联的需求编号列表，只能使用需求文档中出现的编号"
        req_section = f"\n# 需求文档\n{requirements}\n"
    else:
        req_rule = '关联的接口列表，每项写成 "METHOD /path"，例如 "PATCH /learners/{id}"，必须和接口文档 paths 中的写法完全一致'
        req_section = ""
    system = (SYSTEM_PROMPT
              .replace("__AND_REQS__", "和需求文档" if requirements else "")
              .replace("__REQ_RULE__", req_rule)
              .replace("__TIMEOUT__", f"{timeout:g}")
              .replace("__EXAMPLE__", EXAMPLE.read_text(encoding="utf-8")))
    user = (USER_PROMPT
            .replace("__OPENAPI__", openapi)
            .replace("__REQUIREMENTS_SECTION__", req_section)
            .replace("__COVER__", "所有需求" if requirements else "所有接口")
            .replace("__N__", str(n)))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
