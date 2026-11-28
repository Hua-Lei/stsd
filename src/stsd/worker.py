'''常驻执行器进程入口。

容器或服务器上运行 ``python -m stsd.worker``：初始化数据库表，装配一个
项目的 TaskList 与执行器，然后启动 worker 循环。任务入队仍由 API 或调用方
通过 ``ExecutionContext.executor.exec_task`` 完成；本入口只负责消费。
'''

from __future__ import annotations

import logging
import os
import signal
import threading

from stsd.access.adapters import orm as access_orm
from stsd.bootstrap import bootstrap_executor
from stsd.config import get_engine, get_session_factory
from stsd.library.adapters import orm as library_orm
from stsd.tasklist.adapters import orm as tasklist_orm

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    project_id = os.environ.get('STSD_PROJECT_ID', '').strip()
    if not project_id:
        logger.error('STSD_PROJECT_ID is required')
        return 2

    engine = get_engine()
    access_orm.metadata.create_all(engine)
    library_orm.metadata.create_all(engine)
    tasklist_orm.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    context = bootstrap_executor(session_factory, project_id)

    stop = threading.Event()

    def handle_signal(signum: int, _frame: object) -> None:
        logger.info('received signal %s, stopping', signum)
        stop.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    context.executor.start()
    logger.info('executor worker started for project %s', project_id)
    try:
        while not stop.wait(1.0):
            pass
    finally:
        context.executor.stop(timeout=30)
        engine.dispose()
    logger.info('executor worker stopped')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
