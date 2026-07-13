# main 分支自动部署到小车

结论：可以实现，但不能用普通 GitHub 云端 runner 直接 SSH 到小车。

小车在手机热点/局域网内，地址是 `192.168.x.x` 私网地址，GitHub 托管 runner 无法直接访问。最短闭环方案是在能访问小车的 Windows 笔记本或 Ubuntu 虚拟机上安装 GitHub self-hosted runner，然后由 GitHub Actions 在 `main` CI 通过后调用部署脚本，把代码部署到：

```text
/home/jetson/Project/car10th
```

## 已加入的流水线

- `.github/workflows/mobile_app_ci.yml`
  - `dev` push 时跑 CI
  - `main` push 时跑 CI
  - PR 到 `dev` / `main` 时跑 CI
- `.github/workflows/deploy_robot_main.yml`
  - `Project CI` 在 `main` 成功后自动部署
  - 也支持手动 `workflow_dispatch`
  - 运行环境要求：`self-hosted` + `windows`

部署 workflow 复用现有脚本：

```text
scripts/deploy_robot_agent.ps1
```

因此小车端仍然采用 release 目录加 `current` 软链接的方式，成功后会写入：

```text
/home/jetson/Project/car10th/current/DEPLOYED_COMMIT
```

## GitHub Secrets / Variables

进入 GitHub 仓库：

```text
Settings -> Secrets and variables -> Actions
```

必须配置 Secrets：

| 名称 | 示例 | 说明 |
| --- | --- | --- |
| `ROBOT_HOST` | `192.168.137.239` | 当前小车 IP，变化后要更新 |
| `ROBOT_SSH_PRIVATE_KEY` | 私钥全文 | self-hosted runner 用它免密登录小车 |
| `MQTT_HOST` | `192.168.137.xxx` | 小车能访问到的 MQTT broker 地址 |

建议配置 Variables：

| 名称 | 默认值 | 说明 |
| --- | --- | --- |
| `ROBOT_USER` | `jetson` | 小车用户名 |
| `ROBOT_SSH_PORT` | `22` | SSH 端口 |
| `ROBOT_REMOTE_DIR` | `/home/jetson/Project/car10th` | 小车部署目录 |
| `MQTT_PORT` | `1883` | MQTT 端口 |
| `ROBOT_CODE` | `robot_001` | 小车编号 |

可选 Secrets：

| 名称 | 默认值 |
| --- | --- |
| `MQTT_ROBOT_USERNAME` | `parking_robot` |
| `MQTT_ROBOT_PASSWORD` | `parking_robot_dev` |

## 小车端首次准备

在 Windows 上生成专用部署密钥：

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\car10th_robot_deploy -C car10th-deploy
```

把公钥安装到小车：

```powershell
type $env:USERPROFILE\.ssh\car10th_robot_deploy.pub | ssh jetson@192.168.137.239 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

测试免密：

```powershell
ssh -i $env:USERPROFILE\.ssh\car10th_robot_deploy jetson@192.168.137.239 "hostname && pwd"
```

把私钥文件 `car10th_robot_deploy` 的全文填到 GitHub Secret：

```text
ROBOT_SSH_PRIVATE_KEY
```

首次部署如果需要安装 systemd 服务，可以先在本机手动跑一次：

```powershell
.\scripts\deploy_robot_agent.ps1 `
  -RobotHost 192.168.137.239 `
  -RobotUser jetson `
  -IdentityFile $env:USERPROFILE\.ssh\car10th_robot_deploy `
  -RemoteDir /home/jetson/Project/car10th `
  -MqttHost <小车能访问到的MQTT主机IP> `
  -RobotCode robot_001 `
  -InstallService
```

后续 GitHub 自动部署只负责更新代码和重启服务。

## 安装 self-hosted runner

推荐装在 Windows 笔记本上，因为它已经能访问小车 `192.168.137.239:22`。

GitHub 页面路径：

```text
Settings -> Actions -> Runners -> New self-hosted runner -> Windows
```

按 GitHub 页面给出的命令下载、配置、启动 runner。配置完成后，确认 runner 标签里至少有：

```text
self-hosted
windows
```

如果 runner 装在 Ubuntu 虚拟机，需要把 workflow 的 `runs-on` 改成对应标签，并确认 VM 能 SSH 到小车。

## 验证闭环

1. 合并或 push 到 `main`
2. GitHub Actions 先运行 `Project CI`
3. `Project CI` 成功后自动运行 `Deploy Robot Main`
4. 小车上检查：

```bash
cat /home/jetson/Project/car10th/current/DEPLOYED_COMMIT
systemctl status car10th-robot-agent --no-pager
```

## 关键风险

- 小车 IP 会变：`ROBOT_HOST` 需要更新，最好在手机热点或路由侧固定 DHCP。
- GitHub 云端 runner 访问不到私网小车：必须使用同网段 self-hosted runner，或者额外引入 Tailscale/内网穿透。
- 首次安装 systemd 服务可能需要 sudo 密码：建议先手动执行一次带 `-InstallService` 的部署。
- 当前部署脚本只部署 `robot_agent`，不会自动启动你手动列出的 ROS launch：
  - `ros2 launch yahboomcar_astra colorTracker_X3.launch.py`
  - `ros2 launch yahboomcar_nav rtabmap_sync_launch.py`
  - `ros2 launch yahboomcar_slam camera_octomap_launch.py`

如果后续要把这些 ROS 节点也纳入自动部署，需要再加 systemd service 或 docker/compose 编排，但不建议和第一次 CI/CD 打通混在一起做。
