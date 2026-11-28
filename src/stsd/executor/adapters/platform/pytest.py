'''pytest 平台适配器。

平台适配器知道镜像/解释器、依赖怎么装、入口命令怎么拼、JUnit XML 怎么
解析成修订级结论；沙箱端口只知道执行命令和文件进出。
'''

from __future__ import annotations

import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any
from xml.etree import ElementTree

from stsd.executor.errors import EnvironmentBuildFailed, ExecutionTimeout
from stsd.executor.ports import Sandbox, Workspace
from stsd.executor.records import (
    CommandResult,
    EnvironmentSignature,
    PlatformResult,
)
from stsd.shared.implementation import Implementation

REPORT_FILE = '.stsd-report.xml'
_OUTPUT_LIMIT = 4000
_TEST_MESSAGE_LIMIT = 1000


class PytestPlatform:
    kind = 'pytest'

    def __init__(
        self,
        *,
        python: str = sys.executable,
        install_pytest: bool = False,
        install_requirements: bool = True,
        install_timeout: float = 600.0,
    ) -> None:
        self._python = python
        self._install_pytest = install_pytest
        self._install_requirements = install_requirements
        self._install_timeout = install_timeout

    def environment_signature(
        self, implementation: Implementation
    ) -> EnvironmentSignature:
        requirements = implementation.requirements
        return EnvironmentSignature(
            kind=self.kind,
            python_version=requirements.python_version,
            pip=requirements.pip,
        )

    def prepare(
        self, sandbox: Sandbox, implementation: Implementation
    ) -> None:
        if self._install_pytest:
            self._pip_install(sandbox, ('pytest',))

        requirements = implementation.requirements.pip
        if self._install_requirements and requirements:
            sandbox.write_file(
                'requirements.txt', '\n'.join(requirements) + '\n'
            )
            self._pip_install(sandbox, ('-r', 'requirements.txt'))

    def run(
        self,
        workspace: Workspace,
        implementation: Implementation,
        files: Mapping[str, str],
        bindings: Mapping[str, str],
        timeout: float,
    ) -> PlatformResult:
        for path, content in files.items():
            workspace.write_file(path, content)

        environment = {
            'PYTHONUNBUFFERED': '1',
            'PYTHONDONTWRITEBYTECODE': '1',
            **_binding_env(bindings),
        }
        command = [
            self._python,
            '-m',
            'pytest',
            implementation.runtime_spec.main_file,
            f'--junitxml={REPORT_FILE}',
            '-p',
            'no:cacheprovider',
            '-q',
        ]
        result = workspace.run(
            command, env=environment, timeout=timeout
        )
        if result.timed_out:
            raise ExecutionTimeout(
                'pytest timed out'
                + _output_suffix(result)
            )

        try:
            report = workspace.read_file(REPORT_FILE)
        except (OSError, ValueError) as exc:
            return PlatformResult(
                status='error',
                detail={
                    'reason': f'pytest report is missing: {exc}',
                    'exit_code': result.exit_code,
                    'stdout': _tail(result.stdout),
                    'stderr': _tail(result.stderr),
                },
            )

        try:
            return _parse_report(report, result)
        except ElementTree.ParseError as exc:
            return PlatformResult(
                status='error',
                detail={
                    'reason': f'pytest report is not valid XML: {exc}',
                    'exit_code': result.exit_code,
                    'stdout': _tail(result.stdout),
                    'stderr': _tail(result.stderr),
                },
            )

    def _pip_install(
        self, sandbox: Sandbox, arguments: Sequence[str]
    ) -> None:
        result = sandbox.run(
            [
                self._python,
                '-m',
                'pip',
                'install',
                '--disable-pip-version-check',
                '--no-input',
                *arguments,
            ],
            timeout=self._install_timeout,
        )
        if result.timed_out:
            raise EnvironmentBuildFailed(
                'pip install timed out' + _output_suffix(result)
            )
        if result.exit_code != 0:
            raise EnvironmentBuildFailed(
                f'pip install failed with exit code {result.exit_code}'
                + _output_suffix(result)
            )


def _parse_report(
    report: str, result: CommandResult
) -> PlatformResult:
    root = ElementTree.fromstring(report)
    tests: list[dict[str, Any]] = []
    for case in root.iter('testcase'):
        status = 'passed'
        message = ''
        failure = case.find('failure')
        error = case.find('error')
        skipped = case.find('skipped')
        if error is not None:
            status = 'error'
            message = _element_message(error)
        elif failure is not None:
            status = 'failed'
            message = _element_message(failure)
        elif skipped is not None:
            status = 'skipped'
            message = _element_message(skipped)

        tests.append(
            {
                'name': case.get('name', ''),
                'classname': case.get('classname', ''),
                'file': case.get('file', ''),
                'status': status,
                'duration_ms': _duration_ms(case.get('time')),
                'message': message[:_TEST_MESSAGE_LIMIT],
            }
        )

    detail: dict[str, Any] = {
        'tests': tests,
        'exit_code': result.exit_code,
        'stdout': _tail(result.stdout),
        'stderr': _tail(result.stderr),
    }
    if not tests:
        suite = _suite(root)
        if suite is not None and _suite_count(suite, 'errors') > 0:
            detail['reason'] = 'pytest reported errors without test cases'
            return PlatformResult(status='error', detail=detail)
        if suite is not None and _suite_count(suite, 'failures') > 0:
            detail['reason'] = 'pytest reported failures without test cases'
            return PlatformResult(status='failed', detail=detail)
        detail['reason'] = 'pytest collected no tests'
        return PlatformResult(status='error', detail=detail)

    if any(item['status'] == 'error' for item in tests):
        status = 'error'
    elif any(item['status'] == 'failed' for item in tests):
        status = 'failed'
    else:
        status = 'passed'

    suite = _suite(root)
    if suite is not None:
        if _suite_count(suite, 'errors') > 0:
            status = 'error'
        elif status == 'passed' and _suite_count(suite, 'failures') > 0:
            status = 'failed'
    return PlatformResult(status=status, detail=detail)


def _binding_env(bindings: Mapping[str, str]) -> dict[str, str]:
    environment: dict[str, str] = {}
    for name, value in bindings.items():
        key = re.sub(r'[^A-Za-z0-9]', '_', name).strip('_').upper()
        if not key:
            raise ValueError(f'invalid binding name {name!r}')
        environment[f'STSD_{key}'] = str(value)
    return environment


def _element_message(element: ElementTree.Element) -> str:
    message = element.get('message') or ''
    text = element.text or ''
    if message and text:
        return f'{message}\n{text}'
    return message or text


def _duration_ms(value: str | None) -> float:
    try:
        return round(float(value) * 1000, 1)
    except (TypeError, ValueError):
        return 0.0


def _suite(root: ElementTree.Element) -> ElementTree.Element | None:
    if root.tag == 'testsuite':
        return root
    return root.find('testsuite')


def _suite_count(suite: ElementTree.Element, name: str) -> int:
    try:
        return int(suite.get(name, '0') or '0')
    except ValueError:
        return 0


def _tail(text: str) -> str:
    return text[-_OUTPUT_LIMIT:] if len(text) > _OUTPUT_LIMIT else text


def _output_suffix(result: CommandResult) -> str:
    output = (result.stdout + result.stderr).strip()
    return f': {_tail(output)}' if output else ''
