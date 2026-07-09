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

