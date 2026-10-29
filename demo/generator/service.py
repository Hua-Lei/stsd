from dataclasses import dataclass, field

from demo.generator.config import GeneratorConfig
from openai import OpenAI
import json
from demo.generator.prompt import build_messages
from demo.models import TestCase
from pydantic import ValidationError
import re
from validation import static_warnings


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
    requirements: set[str]
    endpoints: list[tuple[str, re.Pattern]]  # (method, path_pattern)
    req_valid: bool



class TestGenerator:
    def __init__(self, config: GeneratorConfig):
        self.config = config
        self.client = OpenAI(api_key = self.config.api_key, base_url = self.config.base_url, timeout = self.config.timeout)
    def generate(self, spec_text: str, requirements: str | None, n: int) -> list[CaseValidationOutcome]:
        resp = self.client.chat.completions.create(
            model=self.config.model,
            messages=build_messages(spec_text, requirements, n, self.config.timeout),
            response_format={"type": "json_object"},
            max_tokens=self.config.max_tokens,
        )

        choice = resp.choices[0]
        content = choice.message.content or ""
        if choice.finish_reason == "length":
            print("警告: 输出被 max_tokens 截断，可以减小 -n 或调大 --max-tokens")

        raw = self._parse_response(content)
        cases = self._validate(raw, ValidationContext(requirements=set(requirements.split()) if requirements else set(), endpoints=[], req_valid=True))
        return cases

    def _parse_response(self, content: str) -> list[dict]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"无法解析为 JSON: {e.msg}") from e
        raw_cases = data.get("cases", []) if isinstance(data, dict) else []
        return raw_cases

    def _validate_one(self, raw: dict, index: int, context: ValidationContext) -> CaseValidationOutcome:
        case_id = raw.get("id") if isinstance(raw, dict) else None
        try:
            case = TestCase.model_validate(raw)
        except ValidationError as e:
            return CaseValidationOutcome(
                index=index, case_id=case_id, raw=raw,
                test_case=None,
                errors=[f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in e.errors()],
            )
        return CaseValidationOutcome(
            index=index, case_id=case_id, raw=raw,
            test_case=case,
            warnings=static_warnings(case, context.requirements, context.endpoints) if context.req_valid else [],
        )

    def _validate(self, raw_cases: list[dict], context: ValidationContext) -> list[CaseValidationOutcome]:
        return [self._validate_one(raw, i, context) for i, raw in enumerate(raw_cases, 1)]