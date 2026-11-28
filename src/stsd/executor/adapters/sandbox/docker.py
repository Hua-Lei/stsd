'''Docker 沙箱（Python Docker SDK）。

容器端口只负责容器生命周期、文件进出和执行命令；镜像选择、依赖安装和
pytest 入口仍由平台适配器负责。SDK 只需要能访问 Docker socket，镜像里
不需要再安装 docker CLI。
'''

from __future__ import annotations

import io
import logging
import posixpath
import tarfile
import threading
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from uuid import uuid4

import docker as docker_sdk
from docker.errors import DockerException, NotFound

from stsd.executor.errors import (
    EnvironmentBuildFailed,
    SandboxBroken,
)
from stsd.executor.records import CommandResult, EnvironmentSignature

ROOT = '/workspace'

logger = logging.getLogger(__name__)


class DockerClient(Protocol):
    '''沙箱需要的 Docker 操作；测试可以注入假实现。'''

    def create_container(
        self,
        image: str,
        *,
        name: str,
        workdir: str,
        network: str | None,
    ) -> Any: ...

    def exec(
        self,
        container: Any,
        argv: Sequence[str],
        *,
        workdir: str,
        env: Mapping[str, str] | None,
        timeout: float | None,
    ) -> CommandResult: ...

    def put_file(
        self,
        container: Any,
        directory: str,
        filename: str,
        content: str,
    ) -> None: ...

    def get_file(self, container: Any, path: str) -> str: ...

    def remove(self, container: Any) -> None: ...

    def close(self) -> None: ...


class SdkDockerClient:
    '''把 Docker SDK 收敛成沙箱需要的几个操作。'''

    def __init__(
        self, client: docker_sdk.DockerClient | None = None
    ) -> None:
        self._client = client or docker_sdk.from_env()

    def create_container(
        self,
        image: str,
        *,
        name: str,
        workdir: str,
        network: str | None,
    ) -> Any:
        options: dict[str, Any] = {
            'image': image,
            'command': ['sleep', 'infinity'],
            'detach': True,
            'auto_remove': True,
            'name': name,
            'working_dir': workdir,
        }
        if network:
            options['network'] = network
        try:
            return self._client.containers.run(**options)
        except DockerException as exc:
            self._cleanup_name(name)
            raise EnvironmentBuildFailed(
                f'failed to start docker image {image}: {exc}'
            ) from exc

    def exec(
        self,
        container: Any,
        argv: Sequence[str],
        *,
        workdir: str,
        env: Mapping[str, str] | None,
        timeout: float | None,
    ) -> CommandResult:
        result: list[tuple[int, Any]] = []
        failure: list[Exception] = []

        def target() -> None:
            try:
                result.append(
                    container.exec_run(
                        list(argv),
                        workdir=workdir,
                        environment=dict(env or {}),
                        demux=True,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - 在线程里交给调用方
                failure.append(exc)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            self._discard(container)
            raise SandboxBroken('docker exec timed out and was discarded')
        if failure:
            raise SandboxBroken('docker exec failed') from failure[0]

        exit_code, output = result[0]
        stdout, stderr = _split_output(output)
        return CommandResult(
            exit_code=exit_code,
            stdout=_decode(stdout),
            stderr=_decode(stderr),
        )

    def put_file(
        self,
        container: Any,
        directory: str,
        filename: str,
        content: str,
    ) -> None:
        payload = content.encode('utf-8')
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            info = tarfile.TarInfo(name=filename)
            info.size = len(payload)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(payload))
        try:
            container.put_archive(directory, buffer.getvalue())
        except DockerException as exc:
            raise SandboxBroken(
                f'failed to write {filename!r} into container'
            ) from exc

    def get_file(self, container: Any, path: str) -> str:
        try:
            stream, _ = container.get_archive(path)
            data = b''.join(stream)
        except NotFound as exc:
            raise FileNotFoundError(path) from exc
        except DockerException as exc:
            raise SandboxBroken(
                f'failed to read {path!r} from container'
            ) from exc

        try:
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                member = next(
                    (
                        item
                        for item in archive.getmembers()
                        if item.isfile()
                    ),
                    None,
                )
                if member is None:
                    raise FileNotFoundError(path)
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise FileNotFoundError(path)
                return extracted.read().decode('utf-8', 'replace')
        except tarfile.TarError as exc:
            raise SandboxBroken(
                f'failed to unpack {path!r} from container'
            ) from exc

    def remove(self, container: Any) -> None:
        try:
            container.remove(force=True)
        except NotFound:
            return
        except DockerException:
            logger.debug('failed to remove container', exc_info=True)

    def close(self) -> None:
        try:
            self._client.close()
        except DockerException:
            logger.debug('failed to close docker client', exc_info=True)

    def _discard(self, container: Any) -> None:
        try:
            container.remove(force=True)
        except Exception:
            logger.debug('failed to discard container', exc_info=True)

    def _cleanup_name(self, name: str) -> None:
        try:
            self._client.containers.get(name).remove(force=True)
        except Exception:
            logger.debug('failed to clean up container', exc_info=True)


class DockerWorkspace:
    def __init__(self, sandbox: DockerSandbox, path: str) -> None:
        self._sandbox = sandbox
        self.path = path

    def write_file(self, path: str, content: str) -> None:
        self._sandbox._write_file(self.path, path, content)

    def read_file(self, path: str) -> str:
        return self._sandbox._read_file(self.path, path)

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        return self._sandbox._run_in(self.path, argv, env, timeout)

    def cleanup(self) -> None:
        self._sandbox._remove_tree(self.path)


class DockerSandbox:
    def __init__(
        self,
        client: DockerClient,
        container: Any,
        image: str,
    ) -> None:
        self._client = client
        self._container = container
        self.image = image
        self._closed = False

    def write_file(self, path: str, content: str) -> None:
        self._write_file(ROOT, path, content)

    def read_file(self, path: str) -> str:
        return self._read_file(ROOT, path)

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        return self._run_in(ROOT, argv, env, timeout)

    def new_workspace(self, name: str) -> DockerWorkspace:
        path = _join(ROOT, name)
        self._exec(('mkdir', '-p', path), timeout=60)
        return DockerWorkspace(self, path)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._client.remove(self._container)

    # ------------------------------------------------------------------ 文件
    def _write_file(self, base: str, path: str, content: str) -> None:
        target = _join(base, path)
        directory = posixpath.dirname(target)
        filename = posixpath.basename(target)
        self._exec(('mkdir', '-p', directory), timeout=60)
        self._client.put_file(
            self._container, directory, filename, content
        )

    def _read_file(self, base: str, path: str) -> str:
        target = _join(base, path)
        return self._client.get_file(self._container, target)

    # ------------------------------------------------------------------ 命令
    def _run_in(
        self,
        base: str,
        argv: Sequence[str],
        env: Mapping[str, str] | None,
        timeout: float | None,
    ) -> CommandResult:
        return self._client.exec(
            self._container,
            argv,
            workdir=base,
            env=env,
            timeout=timeout,
        )

    def _exec(
        self, command: Sequence[str], *, timeout: float | None
    ) -> CommandResult:
        result = self._client.exec(
            self._container,
            command,
            workdir=ROOT,
            env=None,
            timeout=timeout,
        )
        if result.exit_code != 0:
            raise SandboxBroken(
                f'docker command {command[0]!r} failed: '
                f'{_tail(result.stderr)}'
            )
        return result

    def _remove_tree(self, path: str) -> None:
        if self._closed:
            return
        try:
            self._exec(('rm', '-rf', path), timeout=60)
        except SandboxBroken:
            return


class DockerSandboxFactory:
    def __init__(
        self,
        *,
        client: DockerClient | None = None,
        image_prefix: str = 'python',
        network: str | None = None,
    ) -> None:
        self._client = client or SdkDockerClient()
        self._image_prefix = image_prefix
        self._network = network

    def create(self, environment: EnvironmentSignature) -> DockerSandbox:
        image = f'{self._image_prefix}:{environment.python_version}-slim'
        name = f'stsd-sandbox-{uuid4().hex[:12]}'
        try:
            container = self._client.create_container(
                image,
                name=name,
                workdir=ROOT,
                network=self._network,
            )
        except EnvironmentBuildFailed:
            raise
        except Exception as exc:
            raise EnvironmentBuildFailed(
                f'failed to start docker image {image}'
            ) from exc
        return DockerSandbox(self._client, container, image)


def _join(base: str, path: str) -> str:
    if (
        not isinstance(path, str)
        or not path
        or path.startswith('/')
        or '\\' in path
        or '\x00' in path
    ):
        raise ValueError(f'unsafe container path {path!r}')
    if any(part in ('', '.', '..') for part in path.split('/')):
        raise ValueError(f'unsafe container path {path!r}')
    return posixpath.join(base, path)


def _split_output(output: Any) -> tuple[Any, Any]:
    if isinstance(output, tuple) and len(output) == 2:
        return output
    return output, b''


def _decode(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace')
    return str(value)


def _tail(text: str) -> str:
    return text[-4000:] if len(text) > 4000 else text
