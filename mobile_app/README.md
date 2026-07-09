# 地下空间巡检 APP（Flutter）前端脚手架

本目录仅包含“页面骨架 + Mock 数据 + 统一路由/状态管理”的前端代码，用于后端未就绪时先完成答辩展示与联调准备。

当前运行环境未内置 Flutter/Dart，仓库内无法直接编译验证；请在本机已安装 Flutter 的环境中执行下面的步骤运行。

## 本地运行（推荐）

1. 在仓库根目录执行：

```bash
cd mobile_app
flutter pub get
flutter run
```

2. 如需生成 Android/iOS 原生目录（当本目录不是通过 flutter create 创建时）：

```bash
cd mobile_app
flutter create .
flutter pub get
flutter run
```

如果你希望保留当前 `lib/` 代码不被覆盖，建议先备份 `lib/` 目录后再执行 `flutter create .`。

## 默认能力

- 登录与自动登录：本地缓存登录态（示例以角色与 token 模拟）
- 总控首页：统计卡片 + 单车状态卡片 + 快捷入口
- 地图巡检：地图/航点/禁区/轨迹的占位展示 + 单点导航下发入口（Mock）
- 单车遥控：虚拟摇杆占位 + 关键状态展示（Mock）
- 告警中心：列表/筛选/详情/处理备注（Mock）
- 任务配置：航点与路线管理占位 + 定时巡检配置占位
- 历史回放：按日期选择的占位展示
- LLM 对话：聊天 UI + Mock 回复（后续替换为后端网关）
- 系统设置：后端地址/MQTT 地址配置占位 + 退出登录

## 后续对接点（后端出来后替换）

- `lib/data/repository.dart`：将 `MockRepository` 替换为真实的 `ApiRepository`（HTTP + MQTT）
- `lib/app/app_settings.dart`：持久化后端地址/MQTT 地址，用于动态切换环境
- `lib/app/session.dart`：登录接口、token 刷新、权限下发

