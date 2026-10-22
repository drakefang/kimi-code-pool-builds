# Kimi 独立子代理池 2.3.0 验收

日期：2026-10-22。官方基线 `b5e28fd6beac752a2cdcc0ff2f5fdf40e6494fbb`，Node 26.1.0、pnpm 10.33.0，Windows x64。

| 验证 | 实际结果 |
|---|---|
| 原生 core 配置、spawn、独立池 binding/replay、swarm 定向测试 | 196 通过 |
| SDK 配置/TOML | 7 通过 |
| TUI secondary-model 选择器 | 12 通过 |
| core、SDK、CLI TypeScript 类型检查 | 三项通过 |
| 官方 15 个 package 构建与 Windows SEA 构建 | 通过 |
| nxc Rust build / test / clippy / fmt | 四项通过，210 个测试通过 |
| Kimi 工作流回归 | 31 通过 |
| 部署定向回归 | 13 通过 |
| 真实 nxc + 补丁 exe + 隔离 Responses 服务 | 旧重复配置同步为 8 个 canonical 模型，各 ID 仅一条；重复更新零改写；实际四次子代理请求与 Codex 分档一致 |

真实请求观察：主模型 K3/low，T1 为 Go Flash/high，T2、T3 各自为 Go Flash/max，T4 为 K3/max。原生程序成功退出，thinking 偏好保留，普通启动未改写模型配置。

2.3.0 的新增 change-notifier 快照仍是字符串结构；补丁在三个生产入口统一把对象池序列化为固定字段顺序的字符串，保留原持久格式与比较语义。独立审查发现该适配遗漏后已修复，三包类型检查及真实原生多轮请求通过。

补丁还覆盖严格对象池、原生 lifecycle/profile 持久化、replay、primary/fork 继承与主会话 effort 隔离。已有上游其它检查未扩大运行；不宣称全上游套件通过。

未修改日用配置、HOME、会话、PATH 或全局 Git 配置。未调用真实付费上游；8 模型集合与请求绑定在隔离服务验证，TUI 主模型菜单未做人工截图验收。旧历史会话文件未迁移，也未将新绑定 replay 测试表述为旧 alias 会话恢复证明。

固定 GitHub 制品及下载器只复用本次验收的 exe，跨机器无需重新打补丁或编译；安装到日用配置须另行授权。
