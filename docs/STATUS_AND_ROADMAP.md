# 实现状态 & Roadmap


## 代码库状况

1. access、library、tasklist 基本成型
2. 用例库的实现声明、内容寻址文件存储、`SetImplementation` / `get_implementation_files` 已落地
3. 执行器的 Job 队列、worker、本地子进程与 Docker SDK 沙箱、pytest 平台适配器、项目装配和 worker 容器入口已落地
4. 真实 Docker 环境尚未验证；结果系统尚未订阅 `TaskExecCompleted`，Task 启动事件与 Agent 待做

## Roadmap

- [x] 测试点实现声明与文件存储（library）
- [x] 执行器核心：队列、租约、worker、本地/Docker SDK 沙箱、pytest 适配器、worker 容器入口
- [ ] 执行器：真实 Docker 验证、TaskStarted 订阅与启动补齐
- [ ] 结果持久化 & 分析
- [ ] Agent 模块接入
