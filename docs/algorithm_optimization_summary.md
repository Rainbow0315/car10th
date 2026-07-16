# 小车算法优化总结

本文档汇总当前已完成的算法优化工作，覆盖导航 DWA/SLAM 调参闭环、激光避障算法、激光跟随算法三部分。

## 一、导航与 SLAM 相关优化

### 1. 建立多套 DWA 导航配置

已将导航参数拆分为三套可对比配置：

- `n3`：稳定版 DWA，使用 `yahboomcar_nav/params/dwa_nav_params.yaml`
- `n5`：快速版 DWA，使用 `yahboomcar_nav/params/dwa_nav_params_fast.yaml`
- `n6`：候选版 DWA，使用 `yahboomcar_nav/params/dwa_nav_params_candidate.yaml`

这样可以避免每次直接改主配置，方便在实车上做稳定版、快速版、候选版对比。

### 2. 增加导航 launch 与快捷命令

新增或整理了 DWA 相关启动入口：

- `navigation_dwa_launch.py`
- `navigation_dwa_fast_launch.py`
- `navigation_dwa_candidate_launch.py`

并在 `jetson/alias.txt` 中加入：

```bash
n3='ros2 launch yahboomcar_nav navigation_dwa_launch.py'
n5='ros2 launch yahboomcar_nav navigation_dwa_fast_launch.py'
n6='ros2 launch yahboomcar_nav navigation_dwa_candidate_launch.py'
```

### 3. 加入导航指标采集与分析工具

新增了导航测试闭环工具：

- `nav_test_monitor.py`：记录导航运行过程中的速度、距离、卡住、目标完成情况等指标
- `analyze_nav_metrics.py`：分析单条路线测试结果
- `summarize_nav_metrics.py`：汇总多轮测试结果
- `metrics_utils.py`：统一评分、风险判断和指标计算

重点监控指标包括：

- `/cmd_vel` 连续性：命令间隔、最大间隔、断流次数
- 控制平滑度：急加速、急刹、急转次数
- 目标完成情况：是否到达目标、最终距离、路径效率、耗时
- 定位稳定性：AMCL 位姿协方差、位姿跳变
- 安全性：最小障碍距离、近障采样次数、卡住事件

### 4. 增加自动调参与候选参数流程

新增了 DWA 自动调参相关脚本：

- `tune_dwa_profile.py`：根据实测指标生成候选参数
- `accept_dwa_candidate.py`：判断候选参数是否可接受
- `promote_dwa_candidate.py`：将候选参数提升为正式配置
- `validate_nav_profiles.py`：检查配置、launch、快捷命令引用是否一致

调参逻辑会根据问题类型做对应优化：

- 位姿跳变或 AMCL 不稳定：优先提高 AMCL 粒子数、激光束数量
- 控制命令断流：降低 DWA 计算负载，减少采样数或缩短仿真时域
- 控制不平滑：降低加速度/角速度变化，减少急刹和突然转向
- 路径效率差：调整 path/goal 相关权重
- 目标角度误差大：优化目标点旋转与 yaw 对齐

### 5. GMapping 与激光扫描相关优化

新增或整理了：

- `params/slam_gmapping.yaml`
- `scan_filter.py`
- GMapping launch 中的 scan filter 接入

目标是让建图时的激光输入更稳定，减少无效点、噪声点对地图质量的影响。

## 二、激光避障算法优化

优化对象是 `yahboomcar_laser` 包里的 `laser_Avoidance_*` 节点。

### 1. 原始问题

厂商原版避障逻辑主要是简单反应式规则：

- 根据前、左、右障碍点数量进入固定分支
- 遇到正前方障碍时容易固定左转或右转
- 在激光回调中使用 `sleep()`，导致速度命令断续
- 没有速度自适应，接近障碍时仍可能速度偏快
- 部分状态变量未初始化，遥控/开关介入时存在异常风险

### 2. 新增避障控制器

新增：

- `yahboomcar_laser/avoidance_controller.py`
- `yahboomcar_laser/laser_avoidance_node.py`

核心变化：

- 将纯算法和 ROS 节点分离，方便本地单元测试
- 所有 `laser_Avoidance_*` 入口统一复用新控制器
- 保留原命令名，降低上车使用成本

### 3. 优化转向决策

新算法不再固定转向，而是计算左右两侧：

- 障碍点密度
- 最近障碍距离
- 可通行净空评分

当前方有障碍时，小车会选择更空的一侧绕行。

### 4. 加入速度自适应

新增近障减速逻辑：

- 前方距离安全：正常前进
- 前方距离变近但未达到硬避障阈值：逐步降低线速度
- 进入危险距离：停止前进并转向
- 前方激光数据无效：停车保护，避免盲开

### 5. 增加速度平滑

新算法取消回调中的 `sleep()`，改为连续发布平滑后的速度命令。

作用：

- 减少突然猛转
- 减少左右抖动
- 避免速度命令一段一段输出

### 6. 新增可调参数

主要参数：

- `WarningCount`：障碍点数量阈值
- `MinLinear`：绕障时最低前进速度
- `SlowDistanceFactor`：开始减速的距离倍数
- `SmoothFactor`：速度平滑系数
- `TurnHysteresis`：左右净空接近时保持上次方向，减少摆头
- `Debug`：打印调试信息

### 7. 上车测试命令

```bash
ros2 launch yahboomcar_laser laser_Avoidance_a1_X3.launch.py
```

低速调试：

```bash
ros2 launch yahboomcar_laser laser_Avoidance_a1_X3.launch.py linear:=0.25 angular:=0.8 Debug:=true
```

## 三、激光跟随算法优化

优化对象是 `yahboomcar_laser` 包里的 `laser_Tracker_*` 节点。

### 1. 原始问题

厂商原版激光跟随逻辑主要问题：

- 在较宽角度范围内直接取最近点，容易把侧边障碍、墙角当成目标
- PID 的 D 项偏大，且没有滤波、死区、限幅，容易抖动
- 目标丢失时没有稳定处理，可能出现 `min(empty)` 异常或速度不可控
- 旧 `4ROS` 版本存在 `self.laserAngle` 大小写错误

### 2. 新增跟随控制器

新增：

- `yahboomcar_laser/laser_tracker_controller.py`
- `yahboomcar_laser/laser_tracker_node.py`

所有 `laser_Tracker_*` 入口统一复用新控制器：

- `laser_Tracker_a1_X3`
- `laser_Tracker_a1_R2`
- `laser_Tracker_4ROS`
- `laser_Tracker_4ROS_R2`

### 3. 缩小目标搜索角度

默认只在车头前方约 `24` 度范围内寻找跟随目标。

目标筛选不再只看最近距离，而是综合：

- 距离是否接近期望跟随距离
- 角度是否靠近车头中心
- 是否与上一帧目标连续

这样可以减少侧边近障被误认为跟随目标。

### 4. 优化 PID 减少抖动

新增平滑 PID：

- 距离误差死区
- 角度误差死区
- 输出限幅
- D 项低通滤波
- 最终速度命令平滑

效果：

- 目标轻微晃动时不频繁修正
- 前后跟随更柔和
- 左右转向更平滑

### 5. 增加目标丢失重捕逻辑

目标短暂丢失时：

- 不立即停车或崩溃
- 朝上一次目标所在方向低速旋转
- 在更大的重捕角度内尝试重新锁定目标

如果连续丢失超过设定帧数：

- 停止重捕
- 发布安全停车命令

### 6. 新增可调参数

主要参数：

- `LaserAngle`：正常跟随搜索角度，默认 `24.0`
- `ResponseDist`：期望跟随距离，默认 `0.55`
- `TargetMinDist`：目标最小有效距离
- `TargetMaxDist`：目标最大有效距离
- `RecaptureAngle`：重捕角度
- `RecaptureFrames`：连续丢失多少帧后停止重捕
- `RecaptureAngular`：重捕时低速旋转角速度
- `CommandSmooth`：速度平滑系数
- `Debug`：打印跟随状态

### 7. 上车测试命令

```bash
ros2 launch yahboomcar_laser laser_Tracker_a1_X3.launch.py
```

低速调试：

```bash
ros2 launch yahboomcar_laser laser_Tracker_a1_X3.launch.py linear:=0.22 angular:=0.65 Debug:=true
```

## 四、测试与验证

已增加算法单元测试：

- `test_avoidance_controller.py`
- `test_laser_tracker_controller.py`
- `test_nav_metrics_workflow.py`

本地已验证：

```bash
python -m pytest test\test_laser_tracker_controller.py test\test_avoidance_controller.py
```

结果：

```text
12 passed
```

导航测试闭环也已验证过：

```bash
python -m pytest jetson\code\yahboomcar_ws\src\yahboomcar_nav\test\test_nav_metrics_workflow.py
```

结果：

```text
41 passed
```

## 五、相关提交

当前主要算法优化提交：

- `d49b8ca`：优化导航调参与测试闭环
- `d44ef5b`：优化激光避障算法
- `d82b90a`：优化激光跟随算法

## 六、后续建议

后续实车调优建议按下面顺序进行：

1. 先跑 `n3` 稳定版 DWA，采集一条固定路线的基准指标。
2. 再跑 `n5` 快速版 DWA，比较耗时、路径效率、最小障碍距离和卡住次数。
3. 使用 `n6` 候选版做小步调参，不直接覆盖稳定参数。
4. 避障测试先低速开启 `Debug`，观察是否能正确选择更空的一侧绕行。
5. 跟随测试先降低 `linear` 和 `angular`，确认不会误跟侧边障碍，再逐步提高速度。
6. 每次实车改参后记录测试路线、参数、异常现象和指标结果，避免凭感觉调参。
