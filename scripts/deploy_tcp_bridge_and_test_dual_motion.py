from __future__ import annotations

import argparse
import socket
import threading
import time
from pathlib import Path
from typing import Iterable

import paramiko


ROOT = Path(__file__).resolve().parents[1]
ROBOT_USER = "jetson"
ROBOT_PASSWORD = "yahboom"
CONTAINER_NAME = "ros_x3_fixed"
FILES = (
    (
        ROOT / "backend/apps/tcp_car_bridge/main.py",
        "/home/jetson/Project/car10th/backend/apps/tcp_car_bridge/main.py",
    ),
    (
        ROOT / "backend/apps/tcp_car_bridge/audio_player.py",
        "/home/jetson/Project/car10th/backend/apps/tcp_car_bridge/audio_player.py",
    ),
    (
        ROOT / "backend/apps/ros_bridge/publishers/cmd_vel.py",
        "/home/jetson/Project/car10th/backend/apps/ros_bridge/publishers/cmd_vel.py",
    ),
)
FORWARD_FRAME = b"$011504011B#"
STOP_FRAME = b"$011504001A#"
AUDIO_INVALID_VOLUME_FRAME = b"$01330602FF3B#"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy tcp_car_bridge to two robots and optionally run a short dual motion test.",
    )
    parser.add_argument("--car1", default="192.168.137.239")
    parser.add_argument("--car2", default="192.168.137.89")
    parser.add_argument("--car1-domain", default="30")
    parser.add_argument("--car2-domain", default="31")
    parser.add_argument("--port", type=int, default=6001)
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--interval", type=float, default=0.12)
    parser.add_argument("--skip-deploy", action="store_true")
    parser.add_argument(
        "--move",
        action="store_true",
        help="Actually send forward frames before the final stop frames.",
    )
    args = parser.parse_args()

    robots = [
        RobotTarget("robot_001", args.car1, args.car1_domain, args.port),
        RobotTarget("robot_002", args.car2, args.car2_domain, args.port),
    ]

    for robot in robots:
        check_tcp(robot.host, 22, timeout=4)
        check_tcp(robot.host, robot.port, timeout=4)

    if not args.skip_deploy:
        for robot in robots:
            deploy(robot)

    for robot in robots:
        print(f"verify {robot.name} stop/audio on {robot.host}:{robot.port}")
        print("  stop:", send_frame(robot, STOP_FRAME))
        print("  audio invalid:", send_frame(robot, AUDIO_INVALID_VOLUME_FRAME))

    if args.move:
        run_dual_motion(robots, duration=args.duration, interval=args.interval)
    else:
        print("motion skipped; pass --move to run the real dual forward test")


class RobotTarget:
    def __init__(self, name: str, host: str, ros_domain_id: str, port: int) -> None:
        self.name = name
        self.host = host
        self.ros_domain_id = ros_domain_id
        self.port = port


def check_tcp(host: str, port: int, timeout: float) -> None:
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as exc:
        raise SystemExit(f"{host}:{port} is not reachable: {exc}") from exc
    print(f"{host}:{port} reachable in {time.monotonic() - start:.2f}s")


def deploy(robot: RobotTarget) -> None:
    print(f"deploy {robot.name} {robot.host}")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        robot.host,
        username=ROBOT_USER,
        password=ROBOT_PASSWORD,
        timeout=8,
        banner_timeout=8,
        auth_timeout=8,
    )
    try:
        sftp = client.open_sftp()
        for local_path, remote_path in FILES:
            print(f"  put {local_path.relative_to(ROOT)}")
            sftp.put(str(local_path), remote_path)
        sftp.close()
        run_remote(client, restart_command(robot.ros_domain_id))
    finally:
        client.close()


def restart_command(ros_domain_id: str) -> str:
    return f"""
set -e
docker start {CONTAINER_NAME} >/dev/null
docker exec {CONTAINER_NAME} bash -lc "pkill -f '[a]pps.tcp_car_bridge.main' || true"
docker exec -d \\
  -e ROS_DOMAIN_ID={ros_domain_id} \\
  -e ROBOT_TYPE=x3 \\
  -e RPLIDAR_TYPE=a1 \\
  -e PYTHONUNBUFFERED=1 \\
  {CONTAINER_NAME} bash -lc "
source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
cd /root/car10th/backend
python3 -m apps.tcp_car_bridge.main > /tmp/tcp_car_bridge.log 2>&1
"
sleep 1
docker exec {CONTAINER_NAME} bash -lc "pgrep -af '[a]pps.tcp_car_bridge.main'"
"""


def run_remote(client: paramiko.SSHClient, command: str) -> None:
    _, stdout, stderr = client.exec_command(command, timeout=40)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    code = stdout.channel.recv_exit_status()
    if out:
        print(out)
    if code != 0:
        raise RuntimeError(f"remote command failed ({code}): {err or out}")
    if err:
        print(err)


def send_frame(robot: RobotTarget, frame: bytes, timeout: float = 5.0) -> str:
    start = time.monotonic()
    with socket.create_connection((robot.host, robot.port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(frame)
        response = sock.recv(256).decode("ascii", "replace").strip()
    return f"{response} ({time.monotonic() - start:.3f}s)"


def run_dual_motion(
    robots: Iterable[RobotTarget],
    *,
    duration: float,
    interval: float,
) -> None:
    robot_list = list(robots)
    barrier = threading.Barrier(len(robot_list))
    results: dict[str, dict[str, object]] = {}

    def worker(robot: RobotTarget) -> None:
        sent = 0
        responses: list[str] = []
        try:
            with socket.create_connection((robot.host, robot.port), timeout=5) as sock:
                sock.settimeout(0.2)
                barrier.wait(timeout=8)
                try:
                    deadline = time.monotonic() + duration
                    while time.monotonic() < deadline:
                        sock.sendall(FORWARD_FRAME)
                        sent += 1
                        time.sleep(interval)
                finally:
                    for _ in range(3):
                        sent += send_and_collect(sock, STOP_FRAME, responses)
                        time.sleep(0.08)
            results[robot.name] = {
                "ok": True,
                "sent": sent,
                "responses": responses[-5:],
            }
        except Exception as exc:
            results[robot.name] = {
                "ok": False,
                "sent": sent,
                "error": repr(exc),
                "responses": responses[-5:],
            }

    threads = [
        threading.Thread(target=worker, args=(robot,), daemon=True)
        for robot in robot_list
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    for name in sorted(results):
        print(name, results[name])
    if not all(result.get("ok") for result in results.values()):
        raise SystemExit("dual motion test failed")


def send_and_collect(sock: socket.socket, frame: bytes, responses: list[str]) -> int:
    sock.sendall(frame)
    try:
        response = sock.recv(64).decode("ascii", "replace").strip()
    except socket.timeout:
        response = "NO_RESPONSE"
    responses.append(response)
    return 1


if __name__ == "__main__":
    main()
