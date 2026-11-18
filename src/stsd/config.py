'''
应用配置与数据库连接的辅助函数。
'''

import sqlite3

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


class DbSettings(BaseSettings):
    '''从环境变量读取：STSD_DB_URL。'''
    model_config = SettingsConfigDict(env_prefix='STSD_')

    db_url: str = 'sqlite:///stsd.db'


def get_engine(url: str | None = None) -> Engine:
    '''url 缺省时取 STSD_DB_URL。测试可传 "sqlite://" 得到内存库。'''
    engine = create_engine(url or DbSettings().db_url)
    if engine.dialect.name == 'sqlite':
        # SQLite 默认不检查外键，每个新连接都要打开。
        @event.listens_for(engine, 'connect')
        def _enable_foreign_keys(dbapi_conn: sqlite3.Connection, _) -> None:
            dbapi_conn.execute('PRAGMA foreign_keys=ON')
    return engine


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    '''提交后不让对象过期，这样工作单元关闭会话后，调用方仍能读取返回的实体。'''
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False)
