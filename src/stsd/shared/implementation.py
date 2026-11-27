"""测试点实现声明。

一条实现声明说明它跑在哪个平台、由哪些文件构成、需要什么环境、执行时
要填入哪些绑定。声明只保存包内路径和内容哈希，文件内容由用例库的
``get_implementation_files`` 读取，形状见 docs/contracts/implementation-spec.md。
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

PYTEST_KIND = 'pytest'
PYTEST_BASE_URL = 'base_url'

_HASH_RE = re.compile(r'^sha256:[0-9a-f]{64}$')
_PYTHON_VERSION_RE = re.compile(r'^\d+\.\d+(?:\.\d+)?$')


class InvalidImplementation(ValueError):
    """实现声明的形状或取值不合法。"""


def hash_content(content: str) -> str:
    """返回 ``sha256:<hex>`` 形式的内容哈希。"""
    if not isinstance(content, str):
        raise InvalidImplementation('file content must be a string')
    return 'sha256:' + hashlib.sha256(content.encode('utf-8')).hexdigest()


def is_content_hash(value: object) -> bool:
    return isinstance(value, str) and bool(_HASH_RE.fullmatch(value))


def _validate_content_hash(value: object) -> str:
    if not is_content_hash(value):
        raise InvalidImplementation(
            'content_hash must look like sha256:<64 hex characters>'
        )
    return value


def _validate_path(value: object, field: str = 'path') -> str:
    if not isinstance(value, str) or not value:
        raise InvalidImplementation(f'{field} must not be empty')
    if value.startswith('/') or '\\' in value or '\x00' in value:
        raise InvalidImplementation(
            f'{field} must be a relative POSIX path'
        )
    if any(part in ('', '.', '..') for part in value.split('/')):
        raise InvalidImplementation(
            f'{field} must not contain empty, "." or ".." segments'
        )
    return value


def _as_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidImplementation(f'{field} must be an object')
    return value


@dataclass(frozen=True)
class File:
    """实现包里的一个文件，身份是包内路径，内容由哈希定位。"""

    path: str
    content_hash: str

    def __post_init__(self) -> None:
        _validate_path(self.path)
        _validate_content_hash(self.content_hash)

    def to_dict(self) -> dict[str, str]:
        return {'path': self.path, 'content_hash': self.content_hash}

    @classmethod
    def from_dict(cls, data: object) -> File:
        raw = _as_mapping(data, 'file')
        try:
            path = raw['path']
            content_hash = raw['content_hash']
        except KeyError as exc:
            raise InvalidImplementation(
                f'file is missing {exc.args[0]!r}'
            ) from exc
        return cls(path=path, content_hash=content_hash)


@dataclass(frozen=True)
class Package:
    """一份实现携带的文件集合；按路径排序，路径唯一。"""

    files: tuple[File, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.files, tuple) or not self.files:
            raise InvalidImplementation(
                'package must contain at least one file'
            )
        if not all(isinstance(item, File) for item in self.files):
            raise InvalidImplementation('package files must be File objects')
        paths = [item.path for item in self.files]
        if len(set(paths)) != len(paths):
            raise InvalidImplementation('package has duplicate file paths')
        object.__setattr__(
            self, 'files', tuple(sorted(self.files, key=lambda item: item.path))
        )

    def paths(self) -> frozenset[str]:
        return frozenset(item.path for item in self.files)

    def to_dict(self) -> dict[str, list[dict[str, str]]]:
        return {'files': [item.to_dict() for item in self.files]}

    @classmethod
    def from_dict(cls, data: object) -> Package:
        raw = _as_mapping(data, 'source')
        files = raw.get('files')
        if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
            raise InvalidImplementation('source.files must be a list')
        return cls(tuple(File.from_dict(item) for item in files))

    @classmethod
    def from_files(cls, files: Mapping[str, str]) -> Package:
        """按 ``{路径: 内容}`` 建立包，并计算每个文件的内容哈希。"""
        if not isinstance(files, Mapping) or not files:
            raise InvalidImplementation('files must be a non-empty mapping')
        entries: list[File] = []
        for path, content in files.items():
            _validate_path(path)
            if not isinstance(content, str):
                raise InvalidImplementation(
                    f'file content for {path!r} must be a string'
                )
            entries.append(File(path=path, content_hash=hash_content(content)))
        return cls(tuple(entries))


def package_from_files(files: Mapping[str, str]) -> Package:
    return Package.from_files(files)


@dataclass(frozen=True)
class PytestRequirements:
    """pytest 实现要求的构建环境：python 版本与 pip 依赖行。"""

    python_version: str
    pip: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.python_version, str) or not (
            _PYTHON_VERSION_RE.fullmatch(self.python_version)
        ):
            raise InvalidImplementation(
                'python_version must look like "3.14"'
            )
        if isinstance(self.pip, (str, bytes)) or not isinstance(
            self.pip, Sequence
        ):
            raise InvalidImplementation('pip must be a list of strings')
        lines: list[str] = []
        for line in self.pip:
            if not isinstance(line, str):
                raise InvalidImplementation('pip must be a list of strings')
            stripped = line.strip()
            if not stripped:
                continue
            if '\n' in stripped or '\r' in stripped:
                raise InvalidImplementation(
                    'each pip requirement must be a single line'
                )
            if stripped.startswith('-'):
                raise InvalidImplementation(
                    'pip requirement lines must not start with "-"'
                )
            lines.append(stripped)
        object.__setattr__(self, 'pip', tuple(sorted(set(lines))))

    def to_dict(self) -> dict[str, Any]:
        return {
            'python_version': self.python_version,
            'pip': list(self.pip),
        }

    @classmethod
    def from_dict(cls, data: object) -> PytestRequirements:
        raw = _as_mapping(data, 'requirements')
        python_version = raw.get('python_version')
        pip = raw.get('pip', [])
        if not isinstance(pip, Sequence) or isinstance(pip, (str, bytes)):
            raise InvalidImplementation('requirements.pip must be a list')
        return cls(python_version=python_version, pip=tuple(pip))


@dataclass(frozen=True)
class PytestRuntimeSpec:
    """pytest 实现怎么运行：入口文件。"""

    main_file: str

    def __post_init__(self) -> None:
        _validate_path(self.main_file, 'main_file')

    def to_dict(self) -> dict[str, str]:
        return {'main_file': self.main_file}

    @classmethod
    def from_dict(cls, data: object) -> PytestRuntimeSpec:
        raw = _as_mapping(data, 'runtime_spec')
        try:
            main_file = raw['main_file']
        except KeyError as exc:
            raise InvalidImplementation(
                'runtime_spec is missing "main_file"'
            ) from exc
        return cls(main_file=main_file)


@dataclass(frozen=True)
class Implementation:
    """一条修订携带的实现声明。

    平台标识当前只接受 pytest；requirements/runtime_spec 的形状随 kind 而定。
    文件内容不在声明里，``source`` 只保存路径和内容哈希。
    """

    kind: str
    source: Package
    requirements: PytestRequirements
    runtime_spec: PytestRuntimeSpec
    inputs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind != PYTEST_KIND:
            raise InvalidImplementation(
                f'unsupported implementation kind {self.kind!r}'
            )
        if not isinstance(self.source, Package):
            raise InvalidImplementation('source must be a Package')
        if not isinstance(self.requirements, PytestRequirements):
            raise InvalidImplementation(
                'requirements must be PytestRequirements'
            )
        if not isinstance(self.runtime_spec, PytestRuntimeSpec):
            raise InvalidImplementation(
                'runtime_spec must be PytestRuntimeSpec'
            )
        if isinstance(self.inputs, (str, bytes)) or not isinstance(
            self.inputs, Sequence
        ):
            raise InvalidImplementation('inputs must be a list of names')
        names = tuple(self.inputs)
        if not names or any(
            not isinstance(name, str) or not name.strip() for name in names
        ):
            raise InvalidImplementation('inputs must contain non-empty names')
        if len(set(names)) != len(names):
            raise InvalidImplementation('inputs must not contain duplicates')
        object.__setattr__(self, 'inputs', names)
        if names != (PYTEST_BASE_URL,):
            raise InvalidImplementation(
                'pytest implementation inputs must be ("base_url",)'
            )
        if self.runtime_spec.main_file not in self.source.paths():
            raise InvalidImplementation(
                'runtime_spec.main_file must be one of the source files'
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            'kind': self.kind,
            'source': self.source.to_dict(),
            'requirements': self.requirements.to_dict(),
            'runtime_spec': self.runtime_spec.to_dict(),
            'inputs': list(self.inputs),
        }

    @classmethod
    def from_dict(cls, data: object) -> Implementation:
        raw = _as_mapping(data, 'implementation')
        try:
            kind = raw['kind']
            source = raw['source']
            requirements = raw['requirements']
            runtime_spec = raw['runtime_spec']
            inputs = raw['inputs']
        except KeyError as exc:
            raise InvalidImplementation(
                f'implementation is missing {exc.args[0]!r}'
            ) from exc
        if not isinstance(inputs, Sequence) or isinstance(
            inputs, (str, bytes)
        ):
            raise InvalidImplementation('inputs must be a list of names')
        return cls(
            kind=kind,
            source=Package.from_dict(source),
            requirements=PytestRequirements.from_dict(requirements),
            runtime_spec=PytestRuntimeSpec.from_dict(runtime_spec),
            inputs=tuple(inputs),
        )


def validate_implementation(value: object) -> Implementation:
    """重新校验一份已构造的声明，供冻结等闸口使用。"""
    if not isinstance(value, Implementation):
        raise InvalidImplementation(
            'implementation must be an Implementation'
        )
    return Implementation(
        kind=value.kind,
        source=Package.from_dict(value.source.to_dict()),
        requirements=PytestRequirements.from_dict(
            value.requirements.to_dict()
        ),
        runtime_spec=PytestRuntimeSpec.from_dict(
            value.runtime_spec.to_dict()
        ),
        inputs=tuple(value.inputs),
    )
