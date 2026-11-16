# OpenClaw 自定义工具镜像

基于 **OpenClaw 官方带浏览器镜像**增加少量工具，不 Fork、不下载或编译 OpenClaw 源码。

当前 Dockerfile 默认底座为官方 `2026.11.4-browser`，已锁定 manifest SHA-256。
GitHub Actions 会独立查询最新正式 Release，确认对应 browser 镜像与 amd64 平台存在后，再按 digest 构建。

## 增加的工具

| 软件包 | 用途 |
| --- | --- |
| `vim` | 提供 `vim` 编辑命令 |
| `netcat-openbsd` | 提供 `nc`，支持 SSH 经 HTTP CONNECT / SOCKS5 代理 |
| `ffmpeg` | 视频、音频与抽帧工具 |
| `fonts-noto-cjk` / `fontconfig` | 中文及其他 CJK 字体与字体发现工具 |

OpenClaw、Node、Chromium 及原有运行时由官方底座提供。保留官方 ENTRYPOINT、CMD、健康检查，最终仍使用 `node` 非 root 用户。

## 自动构建与发布

仓库：<https://github.com/Shen-Chris/openclaw-image>

发布目标：`ghcr.io/shen-chris/openclaw-image`

- 修改 main 分支中的构建文件时触发。
- 每日 UTC 01:23（北京时间 09:23）检查官方最新稳定版；GitHub 定时任务可能延迟，不是精确定时服务。
- Actions → **Build official-based OpenClaw image** → **Run workflow** 可手动触发。
- `version=latest`：选择最新稳定版，发布后更新 `candidate`。
- `version=2026.11.4` 等指定版本：仅发布该版本，不移动 `candidate`，避免手动构建旧版本导致候选镜像降级。
- 拒绝 beta/rc 和草稿版本；若 browser 镜像尚未发布或缺少 amd64，任务明确失败，下次再重试，不静默换成普通镜像或 main。
- 相同基础镜像 digest 和构建配方已经发布时跳过重建。检测失败不会被当成已发布；构建或发布失败不会移动 candidate。

版本标签形如：

```text
ghcr.io/shen-chris/openclaw-image:2026.11.4-r1-<配方指纹>
ghcr.io/shen-chris/openclaw-image:candidate
```

标签包含上游版本、配方修订号和基础镜像/构建文件指纹。生产使用确切版本标签，最好再锁定实际发布的镜像 digest；不要让 Watchtower 自动跟随 candidate。

更改软件包或构建逻辑会改变指纹。若只想刷新 Debian 软件包，递增 `image-config.json` 的 `recipe_revision` 再提交；每天检查不会无意义地重复构建同一配方。

**自动发现新版本不会自动修改仓库里的 Dockerfile 默认版本。** 本地默认构建仍使用已审阅的固定底座；CI 使用解析后的 `BASE_IMAGE`。手动更新 Dockerfile 默认 pin 时，同时更新 image-config.json 的 default_version/default_base_digest。

### GitHub 配置与费用

使用 GitHub 托管的 `ubuntu-latest` runner，初期仅构建 `linux/amd64`。工作流不需要服务器 SSH、宝塔凭据、模型密钥或长期 PAT。

发布只使用任务级 `GITHUB_TOKEN`，权限为 `contents: read` 和 `packages: write`。Actions 使用固定 commit SHA；不运行上游源码工作流，不使用 pull_request_target，不从外部 PR 发布镜像。

首次使用需确认仓库允许 Actions 和包写入。GHCR 新包不一定自动公开；需要匿名拉取时，在 GitHub 的包设置中显式设为 Public。私有包请使用只读包凭据拉取，不把凭据写进 Dockerfile。

公开仓库的标准托管 runner 通常可免费使用，但仍受 GitHub 当期计费、用量和存储规则约束。长时间无活动时，公开仓库的 schedule 可能被 GitHub 自动禁用；需在 Actions 中重新启用。

## 本地构建（在有 Docker 的宿主机运行）

```bash
docker build --pull -t local/openclaw:2026.11.4-custom-r1 .
bash scripts/smoke-test.sh local/openclaw:2026.11.4-custom-r1 2026.11.4
```

手动选择其他已核实的官方底座：

```bash
docker build --pull \
  --build-arg BASE_IMAGE='ghcr.io/openclaw/openclaw:<版本>-browser@sha256:<已核实摘要>' \
  -t local/openclaw:<版本>-custom-r1 .
```

查询 CI 将选择的版本（仅公开网络读取，不构建、不发布）：

```bash
python3 scripts/resolve-image.py --version latest --repository Shen-Chris/openclaw-image
```

离线单元测试与脚本语法检查：

```bash
python3 -m unittest discover -s tests -v
bash -n scripts/smoke-test.sh
```

## 验收范围

构建后先用无网络、无生产挂载、无认证资料的临时容器检查：非 root 用户、OpenClaw 程序版本、vim、nc 代理参数、ffmpeg、中文字体查询以及 Chromium 可执行文件。全部通过后才发布版本标签。

这不是生产环境端到端验收，**不证明**真实浏览器导航、QQ/微信、订阅 OAuth、MCP 或历史数据迁移成功。

## 生产升级边界

本项目只发布镜像，不自动连接服务器、不切换生产容器、不修改生产 Compose，也不迁移或复制生产数据。

从 `2026.4.14` 升级不能因为换成派生镜像就跳过官方中间版本迁移要求：先依据官方说明使用 `2026.9.5` 处理旧状态，适用的旧格式再经过 `2026.9.7`，在隔离副本验收后再进入目标版本。旧中间版本的 browser 标签是否存在须单独核实，不保证此工作流能为每个历史版本提供 browser 底座。

保留原有持久化路径、环境变量、网络和 Agent 权限。第一次试启动新版不能挂生产状态目录：官方入口可能自动运行 Doctor 并写入状态。回滚必须恢复同一代旧镜像与一致性数据备份，不能只换回旧镜像。

## 安全

- 构建上下文只允许 Dockerfile 和 .dockerignore；不复制本地配置或工作区。
- 不提交或上传 openclaw.json、.env、SSH 私钥、OAuth、机器人凭据、私人记忆或会话。
- SSH 代理地址、私钥路径和生产 Compose 不属于镜像配方，不在这里硬编码。
- 基础镜像按官方公开 manifest 的实际字节校验 SHA-256。基础版本与自定义配方记录在镜像标签和 Actions 摘要中。
- 派生包安装遵循当前 Debian 仓库，并非字节级可复现；长期部署与回滚应保留已发布的镜像 digest。
