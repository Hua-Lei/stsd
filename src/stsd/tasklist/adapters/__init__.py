'''适配器层：把领域/应用层的接口连接到具体技术（SQLAlchemy、外部端口）。'''

from stsd.tasklist.adapters.orm import (
    init_db,
    mapper_registry,
    metadata,
    start_mappers,
    stop_mappers,
)
from stsd.tasklist.adapters.repository import (
    SqlAlchemyTaskListRepository,
    TaskListRepository,
)

__all__ = [
    'init_db',
    'mapper_registry',
    'metadata',
    'start_mappers',
    'stop_mappers',
    'SqlAlchemyTaskListRepository',
    'TaskListRepository',
]
