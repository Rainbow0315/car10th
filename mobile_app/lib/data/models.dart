enum RobotMode {
  patrol,
  follow,
  standby,
}

enum NetworkStatus {
  online,
  offline,
}

class DashboardStats {
  final int onlineRobots;
  final int todayPatrolCount;
  final int highRiskAlarmCount;
  final Map<AlarmType, int> alarmTypeCounts;

  const DashboardStats({
    required this.onlineRobots,
    required this.todayPatrolCount,
    required this.highRiskAlarmCount,
    required this.alarmTypeCounts,
  });
}

class InspectionMonitorStatus {
  final bool running;
  final String topicName;
  final double intervalSec;
  final int totalFrames;
  final int totalAlarmFrames;
  final int totalAlarms;
  final DateTime? startedAt;
  final DateTime? lastCheckedAt;
  final DateTime? lastAlarmAt;
  final String? lastError;

  const InspectionMonitorStatus({
    required this.running,
    required this.topicName,
    required this.intervalSec,
    required this.totalFrames,
    required this.totalAlarmFrames,
    required this.totalAlarms,
    this.startedAt,
    this.lastCheckedAt,
    this.lastAlarmAt,
    this.lastError,
  });
}

class RobotStatus {
  final String robotId;
  final int batteryPercent;
  final NetworkStatus network;
  final RobotMode mode;
  final double speedMps;
  final int latencyMs;

  const RobotStatus({
    required this.robotId,
    required this.batteryPercent,
    required this.network,
    required this.mode,
    required this.speedMps,
    required this.latencyMs,
  });
}

enum AlarmType {
  water,
  crack,
  debris,
  smoking,
}

enum RiskLevel {
  low,
  medium,
  high,
}

enum AlarmStatus {
  unhandled,
  handled,
}

class MapPoint {
  final double x;
  final double y;
  final double yaw;

  const MapPoint({
    required this.x,
    required this.y,
    required this.yaw,
  });
}

class AlarmEvent {
  final String id;
  final AlarmType type;
  final RiskLevel risk;
  final AlarmStatus status;
  final double confidence;
  final DateTime timestamp;
  final MapPoint point;
  final String imagePath;
  final String? robotCode;
  final String? cameraCode;
  final String? detectionModel;
  final String? detectionLabel;
  final List<double> bbox;
  final String? remark;

  const AlarmEvent({
    required this.id,
    required this.type,
    required this.risk,
    required this.status,
    required this.confidence,
    required this.timestamp,
    required this.point,
    required this.imagePath,
    this.robotCode,
    this.cameraCode,
    this.detectionModel,
    this.detectionLabel,
    this.bbox = const [],
    this.remark,
  });

  AlarmEvent copyWith({
    AlarmStatus? status,
    String? remark,
  }) {
    return AlarmEvent(
      id: id,
      type: type,
      risk: risk,
      status: status ?? this.status,
      confidence: confidence,
      timestamp: timestamp,
      point: point,
      imagePath: imagePath,
      robotCode: robotCode,
      cameraCode: cameraCode,
      detectionModel: detectionModel,
      detectionLabel: detectionLabel,
      bbox: bbox,
      remark: remark ?? this.remark,
    );
  }
}

class Waypoint {
  final String id;
  final String name;
  final MapPoint point;

  const Waypoint({
    required this.id,
    required this.name,
    required this.point,
  });
}

class PatrolRoute {
  final String id;
  final String name;
  final List<String> waypointIds;

  const PatrolRoute({
    required this.id,
    required this.name,
    required this.waypointIds,
  });
}

class ChatMessage {
  final String id;
  final DateTime timestamp;
  final bool isUser;
  final String text;

  const ChatMessage({
    required this.id,
    required this.timestamp,
    required this.isUser,
    required this.text,
  });
}
