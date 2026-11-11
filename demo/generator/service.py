import json
import logging
import re
from dataclasses import dataclass, field

from openai import OpenAI
from pydantic import ValidationError

from demo.generator.config import GeneratorConfig
from demo.generator.process import endpoint_ids, load_routes
from demo.generator.prompt import build_messages
from demo.generator.validation import static_warnings
from demo.models import TestCase

logger = logging.getLogger(__name__)


@dataclass
class CaseValidationOutcome:
    index: int
    case_id: str | None
    raw: dict
    test_case: TestCase | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:      # 用 property，别存字段，避免状态不一致
        return self.test_case is not None


@dataclass
class ValidationContext:
    valid_ids: set[str]  # 有需求文档时是需求编号，否则是 "METHOD /path"
    routes: list[tuple[str, re.Pattern]]  # (method, path_pattern)


class TestGenerator:
    def __init__(self, config: GeneratorConfig):
        self.config = config
        self.client = OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=config.timeout)

    def generate(
        self, spec: dict, requirements: str | None, n: int, request_timeout: float
    ) -> list[CaseValidationOutcome]:
        """spec 是已经 filter_spec 过的 OpenAPI 文档；request_timeout 写进提示词，应与执行器一致。"""
        resp = self.client.chat.completions.create(
            model=self.config.model,
            messages=build_messages(json.dumps(spec, ensure_ascii=False), requirements, n, request_timeout),
            response_format={"type": "json_object"},
            max_tokens=self.config.max_tokens,
        )

        choice = resp.choices[0]
        content = choice.message.content or ""
        if choice.finish_reason == "length":
            logger.warning("输出被 max_tokens 截断，可以减小 n 或调大 max_tokens")

        valid_ids = set(re.findall(r"REQ-\d+", requirements)) if requirements else endpoint_ids(spec)
        return self._validate(self._parse_response(content), ValidationContext(valid_ids, load_routes(spec)))

    def _parse_response(self, content: str) -> list[dict]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"无法解析为 JSON: {e.msg}") from e
        return data.get("cases", []) if isinstance(data, dict) else []

    def _validate_one(self, raw: dict, index: int, context: ValidationContext) -> CaseValidationOutcome:
        case_id = raw.get("id") if isinstance(raw, dict) else None
        try:
            case = TestCase.model_validate(raw)
        except ValidationError as e:
            return CaseValidationOutcome(
                index=index, case_id=case_id, raw=raw,
                errors=[f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()],
            )
        return CaseValidationOutcome(
            index=index, case_id=case_id, raw=raw,
            test_case=case,
            warnings=static_warnings(case, context.valid_ids, context.routes),
        )

    def _validate(self, raw_cases: list[dict], context: ValidationContext) -> list[CaseValidationOutcome]:
        return [self._validate_one(raw, i, context) for i, raw in enumerate(raw_cases, 1)]
