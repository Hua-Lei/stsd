'''实现文件内容的本地内容寻址存储。

文件按 ``sha256`` 哈希存放，相同内容只落一份；内容先写临时文件再原子
替换，避免读到半个文件。这里只负责内容本身，修订与声明的元数据仍由
SQL 保存。
'''

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from stsd.library.domain.errors import (
    ImplementationFileMissing,
    ImplementationInvalid,
    ImplementationStorageError,
)
from stsd.shared.implementation import hash_content, is_content_hash


class LocalFileStore:
    '''把实现文件内容放在本地目录，按 ``sha256`` 寻址。'''

    def __init__(self, root: str | Path) -> None:
        if not str(root):
            raise ValueError('file store root must not be empty')
        self.root = Path(root)

    def put(self, content: str) -> str:
        content_hash = hash_content(content)
        path = self._path(content_hash)
        if path.exists():
            if self._read(path, content_hash) != content:
                raise ImplementationInvalid(
                    f'stored content does not match {content_hash}'
                )
            return content_hash

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle, temp_name = tempfile.mkstemp(
                dir=path.parent, prefix='.tmp-'
            )
            try:
                with os.fdopen(
                    handle, 'w', encoding='utf-8', newline=''
                ) as file:
                    file.write(content)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temp_name, path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
        except OSError as exc:
            raise ImplementationStorageError(
                f'failed to store implementation file {content_hash}'
            ) from exc
        return content_hash

    def get(self, content_hash: str) -> str:
        path = self._path(content_hash)
        if not path.is_file():
            raise ImplementationFileMissing(content_hash)
        return self._read(path, content_hash)

    def exists(self, content_hash: str) -> bool:
        return self._path(content_hash).is_file()

    def _path(self, content_hash: str) -> Path:
        if not is_content_hash(content_hash):
            raise ImplementationInvalid(
                f'invalid content hash {content_hash!r}'
            )
        digest = content_hash.removeprefix('sha256:')
        return self.root / 'sha256' / digest[:2] / digest

    def _read(self, path: Path, expected_hash: str) -> str:
        try:
            content = path.read_text(encoding='utf-8')
        except (OSError, UnicodeError) as exc:
            raise ImplementationFileMissing(expected_hash) from exc
        if hash_content(content) != expected_hash:
            raise ImplementationFileMissing(expected_hash)
        return content
