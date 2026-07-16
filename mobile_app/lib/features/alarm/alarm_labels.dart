import '../../data/models.dart';

String alarmTypeLabel(AlarmType type) {
  switch (type) {
    case AlarmType.water:
      return '积水';
    case AlarmType.crack:
      return '裂缝';
    case AlarmType.debris:
      return '异物';
    case AlarmType.smoking:
      return '其他';
  }
}

String alarmRiskLabel(RiskLevel risk) {
  switch (risk) {
    case RiskLevel.low:
      return '低';
    case RiskLevel.medium:
      return '中';
    case RiskLevel.high:
      return '高';
  }
}

String alarmStatusLabel(AlarmStatus status) {
  switch (status) {
    case AlarmStatus.unhandled:
      return '待处理';
    case AlarmStatus.handled:
      return '已处理';
  }
}

String compactDateTime(DateTime value) {
  final local = beijingDateTime(value);
  String two(int n) => n.toString().padLeft(2, '0');
  return '${local.month}-${two(local.day)} ${two(local.hour)}:${two(local.minute)}';
}

String beijingDateTimeText(DateTime value) {
  final local = beijingDateTime(value);
  String two(int n) => n.toString().padLeft(2, '0');
  return '${local.year}-${two(local.month)}-${two(local.day)} '
      '${two(local.hour)}:${two(local.minute)}:${two(local.second)} UTC+8';
}

DateTime beijingDateTime(DateTime value) {
  if (value.isUtc) {
    return value.toUtc().add(const Duration(hours: 8));
  }
  return value;
}

String alarmDisplayName(AlarmEvent alarm) {
  final label = alarm.detectionLabel?.trim();
  if (label != null && label.isNotEmpty) return label;
  return alarmTypeLabel(alarm.type);
}
