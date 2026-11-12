# 任务清单设计草稿

## 目标

提供一组清单操作原语，上层（人工前端 / LLM 工具）组合成：

`create_list` → `add_items` / `remove_items` → `preview` → `lock_list` → `copy_list`（下一轮回归）

任务清单不生成、不执行用例，只作为"这次测什么"的确定性载体。

## 数据类型

```python

class TaskList:
    tasklist_id: str
    target_software_release_version: int   # 属于清单内容，锁定后不可改
    status: Literal['DRAFT', 'LOCKED']     # 只能 DRAFT -> LOCKED 单向变化
    rev: int                               # 草稿编辑序号，不计入 content_hash
    tasklist_title: str | None             # 元数据，锁定后仍可修改
    content_hash: str | None               # 锁定时固化，DRAFT 状态下为 None
    created_at: datetime
    updated_at: datetime
    source_tasklist_id: str | None         # copy_list 的来源清单
    copy_mode: Literal['RERESOLVE', 'PINNED'] | None

    @property
    def is_editable(self) -> bool:
        pass
    '''status == DRAFT'''

    def compute_content_hash(self, items: list['Item']) -> str:
        pass
    '''目标版本 + 有序的 (use_case_id, use_case_version, content_hash) 集合'''


class CaseRef:
    use_case_id: str
    use_case_version: int
    content_hash: str                      # 加入清单时由服务端从用例库取出，调用方不传
    pinned: bool = False                   # 显式指定版本加入，仅审核展示，不计入 content_hash


class Item:
    seq: int                               # 执行顺序；删除不重排，新增追加
    case_ref: CaseRef

```

字段与存储一一对应：清单与条目分 `tasklists`、`tasklist_items` 两张表；条目以 `(tasklist_id, use_case_id)` 为主键（同一清单内同一条用例只允许一个版本），`(tasklist_id, seq)` 唯一。`content_hash` 为派生字段，`tasklist_id`、`rev` 为分配字段，均不由调用方写入。

| 类别     | 字段                         | 锁定后能否修改            | 计入 content_hash |
| -------- | ---------------------------- | ------------------------- | ----------------- |
| 内容     | 目标版本、条目及顺序         | 否                        | 是                |
| 元数据   | `tasklist_title`             | 是                        | 否                |
| 生命周期 | `status`                     | 只能 DRAFT → LOCKED 单向 | 否                |

## 版本控制

清单里同时有三个"版本"性质的东西：

| 数字               | 含义                       | 何时变化             |
| ------------------ | -------------------------- | -------------------- |
| `use_case_version` | 用例内容的软件版本坐标     | 用例内容被重新确认时 |
| `content_hash`     | 内容指纹（用例级、清单级） | 内容本身变化时       |
| `rev`              | 清单草稿的编辑序号         | 每次成功写入草稿时   |

`use_case_version` 表示"这份用例内容从哪个软件版本起确认可用"，是坐标而不是匹配键，因此目标版本 6 的清单里出现版本 4 的用例是正常状态。

```
resolve(use_case_id, target) =
    在 status = active 且 release_order <= target 的版本中，取 release_order 最大者；
    集合为空返回 NO_APPLICABLE_VERSION，不回退到最早版本；
    用例不存在返回 CASE_NOT_FOUND。
```

只有 `add_items` 与 `copy_list` 会解析并固定版本；`preview` / `get_tasklist` 只在读取时关联 `resolved_version` 展示；`lock_list` 不重新解析。`pin_versions` 显式指定版本时仍由服务端取出内容并标记 `pinned`。

不变量：锁定后内容与条目不可变；同一清单内 `use_case_id` 唯一；版本在加入那一刻固定；元数据可改但不影响指纹。

## 类设计&层级抽象

```
接口层    service   无状态方法：参数校验、编排、结构化返回
事务层    repo      transaction()：以 tasklist_id 为冲突域
持久层    DB        tasklists / tasklist_items
外部端口  port      CaseLibraryPort、RunHistoryPort（由其它模块实现）
```

任务清单不直连用例库或执行结果表，只认端口：`resolve_versions` / `get_versions` / `get_case_briefs`、`get_last_results` / `get_duration_stats`，且均为批量接口。

### 接口

对已锁定清单做编辑产生 `LIST_LOCKED`，对不存在的清单操作产生 `LIST_NOT_FOUND`。除 `create_list` 外，第一个参数一律是 `tasklist_id`。

- `create_list(target_software_release_version, tasklist_title=None)` -> `{tasklist_id, status: 'DRAFT'}`；目标版本必填。
- `copy_list(source_tasklist_id, target_version, mode)` -> `{tasklist_id, status, source_tasklist_id, mode, item_count, rejected[], warnings[]}`。`RERESOLVE` 按新目标版本重新解析，`PINNED` 逐条保留原版本；**解析必须在复制这一刻完成并写入草稿**。
- `add_items(tasklist_id, use_case_ids, pin_versions=None)` -> `{rev, added[], rejected[{use_case_id, code, message}], warnings[]}`；批量添加，默认只传 id、版本由服务端解析，加不进去的进入 `rejected` 而不抛异常。
- `remove_items(tasklist_id, use_case_ids)` -> `{rev, removed[], not_found[]}`；只按 id 删除，剩余 `seq` 不重排。
- `preview(tasklist_id, view='full', page=1, page_size=None)` -> `{summary, items[], diagnostics}`；读取时关联标题、需求、风险、`resolved_version`、`last_run`、`flags`，`errors` 阻塞锁定、`warnings` 不阻塞。无副作用，可反复调用。
- `lock_list(tasklist_id)` -> `{tasklist_id, content_hash, item_count}`；同一事务内完成：校验 DRAFT → 非空 → 版本仍存在 → 内容指纹未变 → 写 LOCKED → 固化 `content_hash`。
- `get_tasklist(tasklist_id)` -> 元数据 + `{item_count, items[]}`；与 `preview` 共用条目投影。
- `rename_list(tasklist_id, tasklist_title)` -> `{tasklist_id, tasklist_title}`；元数据修改，锁定后仍允许。

### 并发

冲突域是 `tasklist_id`：同一清单的写操作按序，不同清单并发；外部端口只读，不参与事务顺序。锁控制作为单独的事务平面，与业务规则分开：

```python
def add_items(tasklist_id, use_case_ids, pin_versions=None):
    with repo.transaction():                       # 等价于 _request('write', path=tasklist_id)
        record = repo.get_for_update(tasklist_id)
        _require_draft(record)
        ...                                        # 校验、解析、写回条目
```

事务开始时即取得清单写锁（SQLite 用 `BEGIN IMMEDIATE`），保证"读清单 → 校验 → 写回"是原子动作；后到的操作若因前一个操作失败（已锁定、已删除），返回对应错误码。`rev` 预留 `expect_rev` 做乐观并发，不一致返回 `REV_CONFLICT`（原型未启用）。

## 错误码

| 错误码                  | 阻塞锁定 | 含义                                  |
| ----------------------- | -------- | ------------------------------------- |
| `TARGET_MISSING`        | 是       | 创建清单时未指定目标版本              |
| `LIST_NOT_FOUND`        | 是       | 清单不存在                            |
| `LIST_LOCKED`           | 是       | 对已锁定清单做编辑操作                |
| `EMPTY_LIST`            | 是       | 空清单不允许锁定                      |
| `DUPLICATE`             | 否       | 该用例已在清单中（返回而非报错）      |
| `CASE_NOT_FOUND`        | 否       | 用例库中无此用例                      |
| `NO_APPLICABLE_VERSION` | 否       | 该用例在目标版本下无适用版本          |
| `VERSION_NOT_FOUND`     | 否       | 引用或 `pin_versions` 指定的版本不存在 |
| `DEPRECATED_REF`        | 否       | 引用了已废弃版本（警告）              |
| `SUPERSEDED`            | 否       | 存在更新的适用版本（警告）            |

`INVALID_ARGUMENT`（参数形状非法）、`CASE_CONTENT_CHANGED`（同版本内容指纹变化）、`REV_CONFLICT`（预留）为实现补充。条目级失败放进 `rejected` / `warnings`，清单级失败抛 `TaskListError`。
