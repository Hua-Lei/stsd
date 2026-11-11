# 目标

基础认知：测试点与用例作为资产维护，测试点本身只是可以断言判断的命题，用以描述如何测试对应功能，但是并不考虑具体实现。用例在测试点经由人工审核确认后，LLM根据测试点的相关信息生成，需要有一定的规约形式，要明确实现测试内容，例如输入、输出、如何执行，结果如何判定。但是考虑到测试的成本和量级，每次测试的时候不一定需要测试全部的用例，因此针对每一次具体的测试应该给出一个任务清单，以期提供可选的用例来完成轻量化或补充性的测试任务。

---

# 设计思想

对于任务清单类的简单设想：

```
TaskList :
	tasklist_id : str
	tasklist_title : str
	target_software_release_version : int
	usecaselist : List[case_ref]
	status : str {'LOCKED' , 'DRAFT'}
    rev : int
    content_hash : str
```

清单中的字段可以按“内容”、“元数据”和“状态”三类区分，它们修改的权限或变化情况不同

| 类别   | 字段                                         | 锁定后能否修改          | 是否计入content_hash |
| ------ | -------------------------------------------- | ----------------------- | -------------------- |
| 内容   | target_software_release_version、usecaselist | 否                      | 是                   |
| 元数据 | tasklist_title                               | 能                      | 否                   |
| 状态   | status                                       | DRAFT -> LOCKED单向变化 | 否                   |

tasklist_id、rev 和 content_hash 均为自动生成/分配数据字段，也不可修改

其中 usecaselist 的顺序是最好是有意义的，例如其就是执行顺序，每一条用例在加入清单是分配一个 seq 并追加至末尾。另外一份清单中应该不允许加入两个 usecase_id 相同的用例，以及同一个 usecase_id 的不同 version 的用例。

任务清单的 content_hash 覆盖“目标软件版本 和 有序的 (usecase_id, usecase_version, content(usecase))集合“，在锁定时计算并固化，防止清单以外发生改动。


对于 case_ref 的一个简单设想：

```
case_ref : 

	use_case_id : str

	use_case_version : int

	contend_hash : str
```

上述 content_hash 为用例内容经规范化后计算出的指纹，由服务器在添加时从用例库取出，调用方不传也不关心。

---



# 1、如何去制作任务清单：

	任务清单可以给测试用户自行勾选，但是考虑效率问题不能够仅由用户选定，可以考虑加入LLM针对当前的项目完成度或更新情况先给出推荐的测试任务清单，用户可以同意或继续进行修改，也可以自己重新生成。以及考虑到分析与推荐的不确定性，同时也可以保留全量测试选项。

	因此这里考虑到需要使用的功能和模块间的协同性，可以抽象出这样的接口功能/工具：用例/测试点库方面需要提供功能例如getCaseInfo()  来查询当前仓库中有哪些测试点/用例，返回信息的程度此处暂时不做非常细致的约束，由于此处需要借助AI来实现任务清单的功能，对于AI是否能够持有前一步生成测试点/用例的记忆会影响到需要得到的信息。例如如果能够保持信息的话，那么用例/测试点只需要返回 id 和 version 即可，但是如果不能够保留记忆的话最好还要返回一些描述此用例/测试点具体是在做什么的信息。可以考虑返回 title 每个用例/测试点使用 title 简单描述一下自身做什么。同时此处需要考虑到人工添加用例进入任务的情景，人工只拿到 id 和 version 的话肯定是不能够制定出想要的任务清单的，所以可能至少还是要返回一个类似于 title 的描述信息。

	另外，为了规范化，人工制作任务清单肯定是通过添加/删除用例来实现的，如果让AI生成任务清单时是一整个生成的话，那么创建任务清单就会有两个不一样的方式，可能不够统一。所以考虑让AI也是使用添加/删除用例来组建生成一个任务清单。对于一个已经创建但未锁定的清单，给出两个接口：

**add_items(tasklist_id, usecase_ids, pin_versions = None)**

**remove_items(tasklist_id, usecase_ids)**

	默认情况下调用时不提供用例的版本号，只提供用例 id ，由服务器解析后回填（具体规则如下）。但是如果有”用户明确要使用某一个版本的用例或旧版本的用例来测试新功能“的场景时，可以通过可选的 pin_versions 显示指定，其形式为 {usecase_id : usecase_version}。这是显示且比较少见的情况，服务器端应该在返回结果中标注该条为 PINNED ，以便审核。

	两个接口均返回可读的结果，而不是仅有成功或失败。例如：

```
add_items(...)->
{
	rev,
    added : [case_ref],
    rejected : [{usecase_id, code, message}]
}

remove_items(...)->
{
	rev,
    removed : [usecase_id]
}
```

	==关于如何解析用例版本，此处需要与用例库及服务器协调，进行一个可能的设计如下：==

```
resolve(usecase_id, target_version) = 
	在 usecase_id 对应的用例可用的情况下，在 usecase_verion <= target_version 的所有版本中，
    选择 usecase_version 最大的；
    若用例集合为空或 target 小于改用例最早版本，报错
```

例如：

```
release_version :   1      2      3      4      5      6
use_case 124    :   v1            v3
use_case 88     :   v1  (此后从未更新)
use_case 210    :                                      v6
```

| 调用            | 结果 | 说明                             |
| --------------- | ---- | -------------------------------- |
| resolve(124, 2) | v1   | v1为此时最新用例                 |
| resolve(124, 6) | v3   | v3为此时最新用例                 |
| resolve(88, 6)  | v1   | v1创建后没有更新过，仍为最新用例 |
| resolve(210, 5) | 报错 | 目标版本小于用例最早可用版本     |

---



# 2、如何保证测试用例的稳定性：

	由于当前用例仓库方面实现预期是对于用例的更新采取版本单独文件更新的方式，而非一个用例文件不同版本反复修改。因此任务清单的实现方式可以不需要采取快照的方式，只需要严格对应好用例的信息 id 和 version 以保证引用关系的稳定性即可。

	所以这里任务清单应该设计为一旦确定（指人工确认创建任务清单）之后就不能够再修改其中记录的有关用例的信息了，并且任务清单记录的用例的 id 和 version 也是不能够在组建任务清单的过程中被修改的，应该只能够是任务清单调用仓库方面关于此功能的接口获得信息后自行记录的。

	这里一个简单的设计是给出 **创建清单接口 create_list(target_software_release_version, tasklist_title = None)** ，调用创建清单接口后清单还处于可编辑状态，可以由AI或人工调用1中提到的功能来编排清单，等到编排完成之后，确认固定此清单时给出 锁定清单接口 **lock_list(tasklist_id)**，一经调用后任务清单即进入锁定状态，不可再被编辑用例相关信息（清单名称等可能还可以修改）。创建好任务清单之后应该允许能够查看任务清单的具体信息，所以给出 **get_tasklist(tasklist_id)** 接口。

	清单的生命周期状态变化示意：

```
（未创建） -> create_list(target_version, task_title) -> DRAFT -> lock_list(tasklist_id) -> LOCKED
```

锁定时一次性完成以下所有动作：校验状态为 DRAFT 、校验清单非空、校验所有条目引用的版本仍然可用、写回清单状态、计算并固化 content_hash 。返回 {tasklist_id, content_hash, item_count}。

---



# 3、对于回归补测的情况下，任务清单应该如何创建：

	比如某一次软件方面的更新只是由于上一次测试发现的问题进行了修正，那么此时的任务清单应该和上一次测试的任务清单相差不多，比如有差异分析的话应该就是剔除上次已经通过的未受影响的用例。或者用户如果想要自己生成一个回归测试的任务清单，如果完全重新编排并不合理，所以考虑可以从上一个任务清单复制一个任务清单，但是此时并没有锁定，而是交由AI进行补测编辑或者用户补测编辑后再锁定。对此需要给出接口 **copy_list(source_tasklist_id, target_software_release_version, mode)。**

| mode      | 语义                                   | 适用场景              |
| --------- | ------------------------------------ | ----------------- |
| PINNED    | 逐条保留原有 (usecase_id, usecase_version) | 同一版本重跑；或用旧断言验证新结构 |
| RERESOLVE | 保留用例 id 集合，按新目标版本重新解析版本              | 常规的下一轮回归，通常是默认    |
|           |                                      |                   |

**注意：RERESOLVE 必须在复制的这一刻完成解析并写入草稿，不能推迟到锁定。** 否则人工审核时看到的是版本 4，锁定后变成版本 6，审核就失去了意义。

另外对于补测场景下LLM分析制定补测任务更合理的方式可能不仅需要获得更新前后的文档，还需要上一次测试的任务清单中具体测试哪些用例的信息以及它们的测试结果。==所以需要能够返回测试清单中的用例信息的功能 **get_items_info({usecase_ids, usecase_versions})**==，测试结果方面应该也需要提供获得测试结果信息的功能 **get_test_result()** 。

```
get_items_info(...) ->
[{
	usecase_id,
    usecase_version,
    usecase_title,
    usecase_ref		# 包括测试什么功能，来源于什么需求等
}
]
```

	这两个接口分别属于用例库模块与执行模块，任务清单只是它们的调用方，此处只记录依赖关系，不定义其具体结构。但有一点必须注意：**上次某条用例通过，不能直接推出"本轮不用测它"。** 判定条件是"同版本或内容未变（content_hash 相同）且通过"，而不是"同 usecase_id 通过"。因为版本 6 的内容可能已经改写过断言，用版本 4 的通过记录为其背书是错的。

---



# 4、人工交互方面的优化考虑：

	当需要人工手动编辑任务清单时，可能考虑是这样，用户可以先预览任务清单制作出的结果是什么样子的，然后可以在预览界面下直接去删除用例，如果要添加的话可能点击添加用例后跳出可选用例库的小窗或页面供用户选择。当用户准备锁定之前也可以再次预览任务清单，防止编辑错误。所以需要给出预览功能 **preview(tasklist_id, view='full', page_size=None)** 。

	prevoew 的职责是把清单里的引用渲染成语义信息。清单里存的是 （usecase_id, usecase_version），而人和 LLM 需要看到的是详细一些的语义信息，例如"这条用例是什么、出自哪个需求"。这些信息应该·在读取时从用例库与执行结果关联得到，不写入清单。

　　它的最小返回结构如下：

```
{
  tasklist_id, status,
  target_software_release_version,
  items : [{
      seq,
      case_ref   : { use_case_id, use_case_version, content_hash },
      title, requirement_ids, risk_level,
      resolved_version,                 -- 此刻按 target 解析出的版本
  }]
}
```

　　需要强调：resolved_version 与 usecase_version 不相等时应该提示。

　　preview 应当无副作用，可以反复调用，只报告问题而不拦截；拦截留给 `lock_list`。

　　另外，preview 与只读接口 get_tasklist 应共用同一套条目投影逻辑：都从 case_ref 关联出展示信息，前者面向草稿并额外附带诊断，后者面向已锁定清单。共用一套投影可以保证两者不会矛盾或混乱。

---

# 5、错误码

| 错误码                   | 是否阻塞锁定 | 含义                    |
| --------------------- | ------ | --------------------- |
| TARGET_MISSING        | 是      | 创建清单时未指定目标版本          |
| LIST_NOT_FOUND        | 是      | 清单不存在                 |
| LIST_LOCKED           | 是      | 对已锁定清单做编辑操作           |
| EMPTY_LIST            | 是      | 空清单不允许锁定              |
| DUPLICATE             | 否      | 该用例已在清单中（返回信息并非报错）    |
| CASE_NOT_FOUND        | 否      | 用例库中无对应用例             |
| NO_APPLICABLE_VERSION | 否      | 该用例在目标版本下无适用版本        |
| VERSION_NOT_FOUND     | 否      | pin_versions 指定的版本不存在 |
| DEPRECATED_REF        | 否      | 引用了已废弃版本（警告）          |
| SUPERSEDED            | 否      | 存在更新的适用版本（警告）         |


