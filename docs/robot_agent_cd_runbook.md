# 小车端自动 CD 配置手册

这份文档面向后续接手项目的人和 AI 助手。读完以后，应当能判断当前 CD 方案是什么、需要哪些信息、如何把任意一台能连接小车的 Windows 电脑配置成部署机，并让 `main` 更新后自动部署到小车。

## 结论先行

当前推荐的长期稳定 CD 链路是：

```text
开发者提交代码
-> GitHub Actions 在 dev / PR 上跑 CI
-> 通过 PR 合并到 main
-> GitHub Actions 派发 CD 任务
-> 实验室 Windows 部署机上的 self-hosted runner 接任务
-> 部署机通过 SSH/SCP 把 main 的代码同步到小车
-> 小车 systemd 重启 car10th-robot-agent
```

关键边界：

- 小车不直接访问 GitHub，也不要求小车安装 git。
- `dev` 只做开发集成和 CI，不自动部署小车。
- 只有 `main` 推送或手动触发 `Robot Agent CD` workflow 时，才允许部署小车。
- GitHub 云端 runner 通常连不到实验室局域网小车，所以 CD 必须由一台能连小车的 self-hosted runner 执行。
- 敏感信息不要写进仓库，统一放到 GitHub Actions Variables / Secrets 或部署机本地 SSH 配置。

## 已有文件

- CD workflow: `.github/workflows/robot_agent_cd.yml`
- 部署脚本: `scripts/deploy_robot_agent.ps1`
- 基础部署说明: `docs/robot_agent_cicd.md`
- 分支和 CI 说明: `docs/github_cicd_setup.md`

`robot_agent_cd.yml` 只会运行在带有以下标签的 GitHub self-hosted runner 上：

```text
self-hosted
Windows
car10th-deployer
```

配置部署机时必须给 runner 加上 `car10th-deployer` 标签，避免误用其他 runner 部署真机。

## 当前实验室示例信息

下面是当前调试环境中出现过的示例值。换机器或换网络后必须重新确认，不要盲填。

```text
小车 SSH 用户: jetson
小车 IP: 192.168.137.239
小车项目根目录: /home/jetson/Project/car10th
小车 robot code: robot_001
MQTT broker 端口: 1883
MQTT robot 用户名: parking_robot
MQTT robot 密码: parking_robot_dev
当前电脑 MQTT host: 192.168.137.51
```

历史网络记录：2026-07-12 曾使用小车 IP `192.168.247.227`、电脑 MQTT host `192.168.247.64`；2026-07-13 切换到当前 `192.168.137.*` 网段。

确认小车信息的命令：

```bash
whoami
pwd
hostname -I
```

确认部署机能连小车：

```powershell
ssh jetson@192.168.137.239
```

确认小车能连 MQTT / 后端：

```bash
ping -c 4 <MQTT_HOST>
nc -vz <MQTT_HOST> 1883
curl http://<MQTT_HOST>:8000/health
```

`ping` 可能被 Windows 防火墙拦截，所以主要看 `nc -vz` 和 `curl`。

## 小车端一次性准备

在小车 Ubuntu 上执行：

```bash
sudo apt update
sudo apt install -y openssh-server python3-venv python3-pip
sudo systemctl enable --now ssh
```

如果希望自动部署时不用手动输入 sudo 密码，需要给部署用户配置仅限本服务的免密 systemd 权限。

先确认 systemctl 路径：

```bash
command -v systemctl
```

编辑 sudoers 文件：

```bash
sudo visudo -f /etc/sudoers.d/car10th-robot-agent
```

写入下面内容，把 `jetson` 和 `/usr/bin/systemctl` 替换成实际值：

```text
jetson ALL=(root) NOPASSWD: /usr/bin/systemctl restart car10th-robot-agent, /usr/bin/systemctl status car10th-robot-agent, /usr/bin/systemctl is-active car10th-robot-agent, /usr/bin/systemctl enable car10th-robot-agent, /usr/bin/systemctl daemon-reload
```

首次安装服务可以通过手动触发 CD 并选择 `install_service=true`，或者在部署机本地执行：

```powershell
.\scripts\deploy_robot_agent.ps1 `
  -RobotHost <小车IP> `
  -RobotUser <小车用户名> `
  -RemoteDir /home/<小车用户名>/Project/car10th `
  -MqttHost <MQTT_HOST> `
  -RobotCode robot_001 `
  -InstallService
```

## 部署机一次性准备

部署机必须满足：

- Windows 系统。
- 能访问 GitHub。
- 能 SSH 到小车。
- 能访问运行 MQTT broker / 后端的电脑 IP。
- 安装 Git、PowerShell、OpenSSH 客户端。
- 已安装并运行 GitHub Actions self-hosted runner。

安装 self-hosted runner 的入口：

```text
GitHub 仓库 -> Settings -> Actions -> Runners -> New self-hosted runner
```

选择 Windows，按 GitHub 页面给出的命令下载、配置并安装 runner。配置时建议：

- runner 名称使用容易识别的名字，例如 `car10th-lab-deployer-01`。
- labels 至少包含 `self-hosted`、`Windows`、`car10th-deployer`。
- 建议作为 Windows Service 运行，保证电脑重启后能自动恢复。
- 运行 runner 的 Windows 用户必须能执行 `ssh`、`scp` 和 `git`。

安装为服务后，确认 runner 在线：

```text
GitHub 仓库 -> Settings -> Actions -> Runners
```

状态应显示 `Idle` 或 `Online`。

## SSH 认证配置

推荐两种方式，二选一即可。

### 方式 A：部署机本地 SSH key

在部署机上用运行 runner 的 Windows 用户生成 SSH key：

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\car10th_robot_agent_ed25519 -C car10th-robot-agent
```

把公钥内容加入小车：

```powershell
type $env:USERPROFILE\.ssh\car10th_robot_agent_ed25519.pub
```

在小车 `~/.ssh/authorized_keys` 追加该公钥。

然后在部署机测试：

```powershell
ssh -i $env:USERPROFILE\.ssh\car10th_robot_agent_ed25519 jetson@192.168.137.239 "hostname && whoami"
```

如果使用这种方式，可以在 GitHub 里不配置 `ROBOT_SSH_PRIVATE_KEY`，但需要确保 runner 用户默认 SSH 配置能找到这把 key，或者后续扩展 workflow 显式传入 key 路径。

### 方式 B：GitHub Secret 保存 SSH private key

把私钥全文保存到 GitHub Secrets：

```text
ROBOT_SSH_PRIVATE_KEY
```

workflow 会在运行时把它写入 runner 临时目录，并传给 `deploy_robot_agent.ps1 -IdentityFile`。这种方式更容易迁移部署机，但私钥进入 GitHub Secrets 后要认真管理仓库权限。

## GitHub Variables / Secrets

进入：

```text
GitHub 仓库 -> Settings -> Secrets and variables -> Actions
```

配置 Variables：

```text
ROBOT_HOST=192.168.137.239
ROBOT_USER=jetson
ROBOT_REMOTE_DIR=/home/jetson/Project/car10th
SSH_PORT=22
MQTT_HOST=192.168.137.51
MQTT_PORT=1883
ROBOT_CODE=robot_001
MQTT_ROBOT_USERNAME=parking_robot
```

配置 Secrets：

```text
MQTT_ROBOT_PASSWORD=parking_robot_dev
ROBOT_SSH_PRIVATE_KEY=<可选，如果采用方式 B 就填写>
```

注意：

- `MQTT_HOST` 不是随便填电脑上看到的任意 IP，而是小车能访问到的那块网卡 IP。
- 如果电脑同时有虚拟机网卡、Docker 网卡、校园网、有线网和热点网卡，要用小车同网段可达的 IP。
- 多车部署时，每台车应使用不同的 `ROBOT_CODE`，也建议拆成不同 workflow 或不同 runner/环境配置，避免覆盖。

## 自动部署怎么触发

自动触发：

```text
push 到 main -> Robot Agent CD 自动运行
```

手动触发：

```text
GitHub 仓库 -> Actions -> Robot Agent CD -> Run workflow
```

手动触发时必须选择 `main` 分支。workflow 内部也加了保护：如果不是 `main`，部署 job 会直接跳过，不会把 `dev` 或其他分支部署到小车。

首次安装或刷新 systemd 服务时，手动触发并勾选：

```text
install_service=true
```

日常部署不要勾选，默认只上传新 release、切换 `current`、重启服务。

## 部署后检查

GitHub Actions 日志中应看到：

```text
Deployment finished.
Deployed commit: <commit>
Robot code: robot_001
MQTT broker: <MQTT_HOST>:1883
```

在部署机或任意能 SSH 小车的电脑上检查：

```powershell
ssh jetson@192.168.137.239 "cat /home/jetson/Project/car10th/current/DEPLOYED_COMMIT"
ssh jetson@192.168.137.239 "systemctl is-active car10th-robot-agent"
ssh jetson@192.168.137.239 "systemctl status car10th-robot-agent --no-pager"
```

在小车上看实时日志：

```bash
journalctl -u car10th-robot-agent -f
```

在后端运行后，从电脑端检查小车是否上线：

```powershell
curl.exe -s http://127.0.0.1:8000/api/fleet/robots
```

预期能看到对应 `robot_code`，并且状态为 `online`。

## 回滚

小车会保留历史 release：

```bash
ls /home/jetson/Project/car10th/releases
```

回滚到旧版本：

```bash
ln -sfn /home/jetson/Project/car10th/releases/<旧release目录> /home/jetson/Project/car10th/current
sudo systemctl restart car10th-robot-agent
cat /home/jetson/Project/car10th/current/DEPLOYED_COMMIT
```

## 常见故障

`No runner matching the specified labels`

说明没有在线 runner 同时满足 `self-hosted`、`Windows`、`car10th-deployer`。检查 runner 是否在线、标签是否拼写一致。

`Permission denied (publickey,password)`

说明 SSH key 没配好。先在部署机本地用同一个 Windows 用户执行 `ssh jetson@<小车IP>`，保证无需人工输入密码或能正常认证。

`sudo: a password is required`

说明小车端 sudoers 没配置，或 `systemctl` 路径不一致。重新执行“小车端一次性准备”的 sudoers 步骤。

`nc -vz <MQTT_HOST> 1883` 失败

说明小车到 MQTT broker 不通。优先检查 `MQTT_HOST` 是否选错网卡 IP，其次检查 Windows 防火墙、Docker Desktop、mosquitto 容器是否运行。

`env file backend/.env not found`

本地 `docker compose` 启动后端依赖时需要 `backend/.env`。小车部署脚本会在 release 中创建或更新 `backend/.env`，但电脑端开发环境仍需要自己的 `backend/.env`。

## 给 AI 助手的执行规则

后续如果用户要求“配置小车自动部署”或“检查 CD”，AI 应先读取本文件，再按以下顺序行动：

1. 确认当前分支和工作区状态，不要误推 `main`。
2. 确认 `.github/workflows/robot_agent_cd.yml` 存在，且只对 `main` / `workflow_dispatch` 部署。
3. 确认部署机 runner 在线并带 `car10th-deployer` 标签。
4. 确认 GitHub Variables / Secrets 是否完整，但不要把 secret 明文写进仓库或日志。
5. 确认部署机能 SSH 到小车，小车能访问 `MQTT_HOST:1883`。
6. 首次部署用 `install_service=true`，日常部署不用。
7. 部署后用 `DEPLOYED_COMMIT`、`systemctl is-active`、`/api/fleet/robots` 三个结果验收。
8. 如果有冲突、权限问题或小车网络不可达，停止并让用户介入真实环境操作。
