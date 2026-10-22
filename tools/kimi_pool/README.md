# Kimi 2.3.0 独立子代理池客户端

Windows x64 单 exe，基于固定官方 Kimi 2.3.0 源码。对象池 choice 只引用真实模型，不加入主模型选择器；子代理的 model/effort 经原生绑定持久化，恢复沿用原绑定。保留官方 2.3.0 功能和旧字符串池读取。

## 跨机器复用

固定发布仓库为 [kimi-code-pool-builds](https://github.com/drakefang/kimi-code-pool-builds)，版本 tag 为 `kimi-2.3.0-pool-v1`。目标机器需要 Python 3.11+、GitHub CLI `gh`；下载不需要 Node、pnpm 或本地编译。

```powershell
python tools/kimi_pool/download.py --output <新的客户端目录>
```

下载器使用同目录 `release-lock.json`，校验 ZIP 与 exe 的发布完整性，已有匹配 exe 可复用。它只下载到显式目录，不更新 PATH、日用 HOME、会话或 nxc 配置。后续安装时才由用户显式把 `[kimi].executable` 指向下载的 exe。

如果只取得发布仓库，检出固定 tag 后使用同样的相对命令。每次升级使用新的 tag 和匹配下载锁，不覆盖旧版本。`nxc kimi` 禁用原生自动升级，避免补丁客户端被替换为不支持对象池的官方程序。

## 维护者重建

`manifest.toml` 固定官方 commit、Node 26.1.0、pnpm 10.33.0；`patches/` 为可重放补丁，`UPSTREAM-LICENSE` 保留上游许可。

```powershell
python tools/kimi_pool/build.py prepare --source <新的源码目录>
python tools/kimi_pool/build.py build --source <源码目录> --output <新的产物目录> --pnpm-script <pnpm.cjs>
```

构建使用官方包构建与 Windows SEA 入口。构建本身不代表验收通过；同一候选须通过配置/绑定 consumer、重放、选择器及隔离真实 nxc 入口后，才添加实际 `verification.json`，再运行：

```powershell
python tools/kimi_pool/package.py --artifact <已验收产物目录> --output <新的发布目录> --repository drakefang/kimi-code-pool-builds --tag kimi-2.3.0-pool-v1
```

ZIP 只包含 `kimi.exe`、`build_info.json`、`verification.json` 和 `LICENSE`。发布与下载摘要仅用于制品完整性，不作为开发或审查准入。验收范围见 [VALIDATION.md](VALIDATION.md)。
