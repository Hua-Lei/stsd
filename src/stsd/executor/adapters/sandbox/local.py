'''本地子进程沙箱。

用于开发与测试：不提供容器隔离，只是把一条执行放进自己的临时目录和独立
进程组，验证命令、超时和文件进出。它不按 python 版本切换解释器；需要
严格环境隔离时换容器实现同一组端口。
'''

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import uuid4

from stsd.executor.errors import SandboxBroken
from stsd.executor.records import CommandResult, EnvironmentSignature


class LocalWorkspace:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write_file(self, path: str, content: str) -> None:
        target = _resolve(self.root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8', newline='')

    def read_file(self, path: str) -> str:
        return _resolve(self.root, path).read_text(encoding='utf-8')

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        return _run_command(argv, self.root, env, timeout)

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


class LocalSandbox:
    def __init__(self, root: Path, environment: EnvironmentSignature) -> None:
        self.root = root
        self.environment = environment

    def write_file(self, path: str, content: str) -> None:
        target = _resolve(self.root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8', newline='')

    def read_file(self, path: str) -> str:
        return _resolve(self.root, path).read_text(encoding='utf-8')

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        return _run_command(argv, self.root, env, timeout)

    def new_workspace(self, name: str) -> LocalWorkspace:
        path = _resolve(self.root, name)
        path.mkdir(parents=True, exist_ok=False)
        return LocalWorkspace(path)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


class LocalSandboxFactory:
    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root) if root is not None else None

    def create(self, environment: EnvironmentSignature) -> LocalSandbox:
        if self._root is None:
            path = Path(
                tempfile.mkdtemp(prefix='stsd-sandbox-')
            )
        else:
            self._root.mkdir(parents=True, exist_ok=True)
            path = self._root / f'sandbox-{uuid4().hex}'
            path.mkdir()
        return LocalSandbox(path, environment)


def _resolve(root: Path, path: str) -> Path:
    if (
        not isinstance(path, str)
        or not path
        or path.startswith('/')
        or '\\' in path
        or '\x00' in path
    ):
        raise ValueError(f'unsafe workspace path {path!r}')
    if any(part in ('', '.', '..') for part in path.split('/')):
        raise ValueError(f'unsafe workspace path {path!r}')
    target = root / path
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'workspace path escapes root: {path!r}')
    return target


def _run_command(
    argv: Sequence[str],
    cwd: Path,
    env: Mapping[str, str] | None,
    timeout: float | None,
) -> CommandResult:
    environment = os.environ.copy()
    if env is not None:
        environment.update({str(key): str(value) for key, value in env.items()})

    try:
        process = subprocess.Popen(
            list(argv),
            cwd=cwd,
            env=environment,
            text=True,
            encoding='utf-8',
            errors='replace',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        return CommandResult(exit_code=127, stdout='', stderr=str(exc))

    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stdout, stderr = _kill_process_group(process)
        return CommandResult(
            exit_code=-9,
            stdout=stdout or '',
            stderr=stderr or '',
            timed_out=True,
        )
    return CommandResult(
        exit_code=process.returncode,
        stdout=stdout or '',
        stderr=stderr or '',
    )


def _kill_process_group(
    process: subprocess.Popen[str],
) -> tuple[str | None, str | None]:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as exc:
        raise SandboxBroken(
            f'failed to kill process group {process.pid}'
        ) from exc

    try:
        return process.communicate(timeout=5)
    except subprocess.TimeoutExpired as exc:
        try:
            process.kill()
        except OSError:
            pass
        raise SandboxBroken(
            f'process group {process.pid} did not die after SIGKILL'
        ) from exc
