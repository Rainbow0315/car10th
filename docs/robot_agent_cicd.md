# 小车端长期稳定部署方案

## 目标

小车 Ubuntu 不能稳定访问 GitHub，因此不让小车直接拉代码。推荐长期部署链路：

```text
GitHub -> Windows 部署机 git pull -> SSH/SCP 同步到小车 -> systemd 重启 robot_agent
```

这个方案的特点：

- 小车不需要安装 git。
- 小车不需要访问 GitHub。
- 每次部署的是 Windows 本地仓库的已提交 `HEAD`。
- 小车端通过 systemd 守护 `robot_agent`，断线或异常退出会自动重启。
- 每次部署会保留历史 release，并把 `current` 软链接切到最新版本。

## 小车端首次准备

在小车 Ubuntu 上安装 SSH、Python venv：

```bash
sudo apt update
sudo apt install -y openssh-server python3-venv python3-pip
sudo systemctl enable --now ssh
```

查看小车 IP 和用户名：

```bash
hostname -I
whoami
```

确认 Windows 能连上小车：

```powershell
ssh <小车用户名>@<小车IP>
```

如果希望后续部署完全无人值守，可以在小车上配置仅针对该服务的免密重启权限：

```bash
command -v systemctl
sudo visudo -f /etc/sudoers.d/car10th-robot-agent
```

写入下面内容，把 `<小车用户名>` 替换成实际用户名，把 `/usr/bin/systemctl` 替换成 `command -v systemctl` 的实际输出：

```text
<小车用户名> ALL=(root) NOPASSWD: /usr/bin/systemctl restart car10th-robot-agent, /usr/bin/systemctl status car10th-robot-agent, /usr/bin/systemctl is-active car10th-robot-agent, /usr/bin/systemctl enable car10th-robot-agent, /usr/bin/systemctl daemon-reload
```

首次安装服务仍可能需要输入一次 sudo 密码；后续部署只需要重启服务时，上面的配置就可以避免手动输密码。

## Windows 端首次部署

在 Windows 项目根目录执行。请替换：

- `<小车IP>`：小车 Ubuntu 的局域网 IP
- `<小车用户名>`：小车 Ubuntu 用户名
- `<电脑IP>`：运行 MQTT broker 且小车能访问到的 Windows IP，例如本次真机测试中小车 `192.168.247.227` 同网段的 `192.168.247.64`

```powershell
cd F:\SHIXUN\car10th

.\scripts\deploy_robot_agent.ps1 `
  -RobotHost <小车IP> `
  -RobotUser <小车用户名> `
  -RemoteDir /home/<小车用户名>/car10th `
  -MqttHost <电脑IP> `
  -RobotCode robot_001 `
  -InstallService
```

首次部署会：

- 打包当前 Git `HEAD`
- 上传到小车 `/home/<小车用户名>/car10th/releases/...`
- 创建或更新小车端 `backend/.env`
- 安装 Python 依赖
- 创建 `current` 软链接
- 安装并启动 systemd 服务 `car10th-robot-agent`

## 后续每次部署

后续代码更新后，在 Windows 上：

```powershell
git pull

.\scripts\deploy_robot_agent.ps1 `
  -RobotHost <小车IP> `
  -RobotUser <小车用户名> `
  -RemoteDir /home/<小车用户名>/car10th `
  -MqttHost <电脑IP> `
  -RobotCode robot_001
```

脚本默认要求工作区干净，也就是先 commit 再部署。这样小车上的版本能和 Git 提交号对应。

如果只是临时试验未提交代码，可以加：

```powershell
-AllowDirty
```

但长期调试不推荐这么做。

## 小车端检查命令

查看当前部署的提交号：

```bash
cat ~/car10th/current/DEPLOYED_COMMIT
```

查看 agent 服务状态：

```bash
systemctl status car10th-robot-agent --no-pager
```

查看实时日志：

```bash
journalctl -u car10th-robot-agent -f
```

重启 agent：

```bash
sudo systemctl restart car10th-robot-agent
```

## 通信检查

在小车上测试到 Windows MQTT broker：

```bash
ping -c 4 <电脑IP>
nc -vz <电脑IP> 1883
curl http://<电脑IP>:8000/health
```

说明：Windows 防火墙可能禁止 ICMP，所以 `ping` 不通不一定代表失败。以 `nc -vz <电脑IP> 1883` 和 `curl http://<电脑IP>:8000/health` 能否成功作为主要判断依据。

预期后端返回：

```json
{"status":"ok","service":"web_api","mqtt_connected":true}
```

在 Windows 上查看小车是否上线：

```powershell
curl.exe -s http://127.0.0.1:8000/api/fleet/robots
```

预期能看到：

```json
"robot_code": "robot_001"
"status": "online"
```

## 多车部署

每台车使用不同 `RobotCode`：

```powershell
.\scripts\deploy_robot_agent.ps1 `
  -RobotHost <小车1IP> `
  -RobotUser <小车用户名> `
  -RemoteDir /home/<小车用户名>/car10th `
  -MqttHost <电脑IP> `
  -RobotCode robot_001 `
  -InstallService

.\scripts\deploy_robot_agent.ps1 `
  -RobotHost <小车2IP> `
  -RobotUser <小车用户名> `
  -RemoteDir /home/<小车用户名>/car10th `
  -MqttHost <电脑IP> `
  -RobotCode robot_002 `
  -InstallService
```

之后就可以用 `/api/fleet/commands/batch` 和 `/api/fleet/formations` 做多车协同测试。

## 回滚思路

小车端 release 会保留在：

```bash
ls ~/car10th/releases
```

如果要回滚到某个旧版本：

```bash
ln -sfn ~/car10th/releases/<旧release目录> ~/car10th/current
sudo systemctl restart car10th-robot-agent
```

回滚后检查：

```bash
cat ~/car10th/current/DEPLOYED_COMMIT
systemctl status car10th-robot-agent --no-pager
```
