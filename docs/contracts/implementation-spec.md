# 实现声明

一条修订至多有一个实现（见 [decisions/002](../decisions/002-implementation-and-freeze.md)）。实现不是一段代码文本，而是一份声明：它说明这份实现跑在哪个平台、由哪些文件构成、需要什么环境、以及执行时需要被填入什么。

当前只有 pytest 一个平台。

## 构成

`Implementation` 由平台标识加四个部分组成：

*   `kind` 平台标识，当前只接受 `pytest`
*   `source` 文件包
*   `requirements` 构建环境的要求，形状随 `kind` 而定
*   `runtime_spec` 怎么运行，形状随 `kind` 而定
*   `inputs` 执行时需要被填入的绑定名，只有名字，没有值

`Package` 是这份实现的文件集合，每个 `File` 是包内路径加内容哈希。文件内容不在声明里，取法见用例库的 `get_implementation_files`。

写入时（`SetImplementation`）随声明一起提交包内路径到内容的映射，用例库按内容计算并校验哈希；落库的声明只保存路径与哈希。读取时 `get_implementation_files` 按哈希取回内容，声明与内容分离不影响调用方拿到的文件集合。

实现挂在修订上，不是挂在测试点上，它的标识是 `(testpoint_id, revision_ver)`。

## pytest

`requirements` 是 python 版本和 pip 依赖行。`runtime_spec` 是 `main_file`，必须是 `source` 里存在的一个路径。`inputs` 是 `("base_url",)`。

执行器把绑定作为环境变量传入容器，`base_url` 对应 `STSD_BASE_URL`。实现从环境变量取得被测地址，不要把地址写进文件。

## 声明、绑定、记录

这三件事发生在三个不同的时刻。实现**声明**它需要哪些绑定，这部分跟着修订冻结，不可变。执行器执行时取值**绑定**，同一条修订换一个环境重跑，变的只是绑定。结果系统**记录**这次实际用的值，否则没法解释一条旧结果当时打的是哪个环境。

`base_url` 为什么不属于冻结内容见 [decisions/008](../decisions/008-implementation-binding-not-frozen.md)。

## 加一个平台

要同时动三处：这份契约里的形状、用例库对形状的校验、执行器里对应的平台适配器。三处都动完才算支持。
