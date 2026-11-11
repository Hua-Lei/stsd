# 用例库设计草稿

## 目标

期望其提供多个操作原语接口，上层编排层组合以支持如shell的文件系统命令：如`ls`,`mkdir`等

## 数据类型

``` python

class LibNode:
    id: int
    parent_id: int
    
    ndtype: Literal['section', 'testpoint']
    '''
    ndtype: node类型
    '''
    
    is_deleted: bool 
    '''
    is_deleted: 软删除标记
    '''


    @property
    def path():
        pass
    '''
    path作为属性实时推导，不在数据库内存储
    '''
    


class TestPointVersion:
    testpoint_id: int                # FK -> LibNode.id, type='testpoint'
    version_no: str                  # 声明当前的测试点是归属哪一个文档版本，与上游提供的文档版本绑定

    name: str
    desc: str                        # 该版本的完整测试内容
    impl_ref: str | NotImplTestCase             # 指向 TestCase 存储id，不内嵌

    created_at: datetime
    updated_by: str                  # 'user:42' / 'agent:sess_xxx'
    change_note: str

    def getTestCase()->TestCase:
        pass
    # PRIMARY KEY (testpoint_id, version_no)

class TestCase:
    id: str
    audited: bool # 当TestPoint修改后自动置false，需要重新审计标记true
    content: JSON # 暂时不展开

```
以上数据类型的字段与数据库存储的声明类型一一对应,其中NotImplTestCase对应到数据库中为NULL

version_no统一都为另外存储文档的文档库对应表声明的版本号
对测试点的修改必须是存在的id+ver_no组合


## 版本控制

用例库作为一个节点树，其中testpoint节点存在一个线性历史绑定到对应节点，section无历史

## 类设计&层级抽象

接口
文件系统管理，并发/锁管理
同步层
DB层——来自persistence模块

### 接口

对外提供如下接口：
tp_id,version_no必须有对应

对于已经软删除的节点，若操作则产生错误


- `getTestPoint(tp_id ,version_no=None)->TestPointVersion`


- `reviseTestPoint(tp_id,version_no,new_tp_info)`
revise后，此版本对应下的impl_ref（若实现），则标记此实现为未审计状态

- `updateTestPoint(tp_id,newversion_no,new_tp_info)`
创建一个(tp_id,newversion_no)的TestPointVersion，此时impl_ref默认为空，不继承前面的TestCase


- `createSection(parent_id,name)`
- `createTestPoint(parent_id,version_no,tp_info)`

- `updateTestCase(tp_id,new_testcase)`

- `getChildren(section_id)->list[LibNode]`
- `deleteNode(id)` 软删除，对于目录，递归标记is_delete
- `moveNode(id, new_parent_id)`



### 并发

冲突检测：path+scope(测试点节点/文件夹子树)
所有操作请求有序，对于不冲突部分并发，冲突部分按序，如果后面的失败（如已经被delete），则返回错误信息

参考设计：锁控制应作为单独的plane与实际文件操作逻辑分开
类似：
def moveNode(id, new_parent_id):
    atomic{
    _request("write", path=_getpath(id), scope=_gettype(id))
    _request("write", path=_getpath(new_parent_id), scope=_gettype(new_parent_id))
    }   
    ...(具体管理node的逻辑)