'''适配器层：把本模块定义的接口接到具体技术上。

stop_mappers 不在这里导出：clear_mappers() 是进程级的，清一次会把
所有模块的映射一起清掉，所以映射的停止只由 stsd.bootstrap.reset_mappers
提供。
'''

from stsd.access.adapters.orm import metadata, start_mappers

__all__ = ['metadata', 'start_mappers']
