# Kimi Code 独立 subagent pool — Windows x64 预览制品

这是由 NxRouter 维护的受控客户端 patch 与构建/下载工具，非 Moonshot 官方发行。
官方源码基线 `f67e6398fb3210ad8ace970e2dfd5bcc984ed61f`（2.1.1），上游为
[MoonshotAI/kimi-code](https://github.com/MoonshotAI/kimi-code)。MIT 许可和原版权通知见 LICENSE。

固定 tag 为 `kimi-2.1.1-pool-v1`。普通环境下载单 SEA `kimi.exe`，无需 Node、pnpm 或重新打包。
需要 Python 3.11+ 和已登录的 GitHub CLI（gh）；从本仓库检出后运行：

```powershell
python tools/kimi_subagent_pool/download.py --release-lock release-lock.json --cache-root <新的专用cache目录>
```

指定 NxRouter 实例以写入受控 executable descriptor（请先保留实例快照）：

```powershell
python tools/kimi_subagent_pool/download.py --release-lock release-lock.json --cache-root <专用cache目录> --write-descriptor --instance-dir <NxRouter实例目录>
```

工具只消费固定 lock，校验 ZIP/exe/recipe/artifact/consumer receipt 和实际能力；不使用 latest，不安装全局 PATH，不修改主控默认模型。ZIP 恰含 kimi.exe、build_info.json、verification.json、LICENSE。下载与能力测试不调用模型。

## 独立 pool 配置语义

`secondary_model.models` 支持旧 string 提示及严格对象 `{model, effort, description}`。
新 key 是 pool-only choice；canonical model 必须已存在并支持明确 effort。
例如多个 choice 可绑定同一个 canonical model 的 low/high/max；不能再为 tier 添加全局 model alias。
Agent.model/AgentSwarm 仍选择 choice，resolver 在创建 child 时绑定 canonical model/effort，并保存至 profile/replay。
主控切换不污染已有 child；pool-bound caller 的 primary 继承其 durable binding；resume/fork 保留绑定及官方 fork 约束。
未知字段、缺失模型和不支持 effort 明确报错，不静默继承或换路由。

## 维护者构建

一次构建供其它 Windows x64 环境下载。需固定 Node 26.1.0、pnpm 10.33.0、Python 和 Git。

```powershell
python tools/kimi_subagent_pool/build.py prepare --source <新的源码目录>
python tools/kimi_subagent_pool/build.py build --source <源码目录> --output <新的产物目录> --node <node.exe> --pnpm-script <pnpm.cjs>
```

recipe 校验官方 SHA、patch、lock、源码 index、工具链，并执行 frozen install、15 package 构建与官方 SEA 流程。
verification.json 只能由维护者在同源码候选真实 consumer/replay 测试通过后生成；不能用静态 capabilities 或 doctor 代替。
升级重新冻结来源并重跑 resolver/profile/request consumer、SDK/TOML/TUI 和构建/下载矩阵，不能只修改版本号。

## 预览验证边界

发布候选已完成五档并行真实 child requester 的 mock/no-model 捕获、primary 下一层继承、持久 replay、fork、撤销模型/effort错误，以及 SDK/TUI/Swarm 定向测试和 SEA 构建。
上游既有 config snapshot 失败及4项 import-boundary 失败在未 patch 基线复现，未宣称完整上游套件通过。
本发布不证明真实 Provider、个人配置迁移或跨平台兼容，不改变 NxRouter 产品 Phase/Gate。
新 binding home 不可仅靠换回旧 exe 或删除 marker 回退；须停止客户端并成对恢复整个迁移前隔离 home 与匹配 artifact/descriptor/config。
