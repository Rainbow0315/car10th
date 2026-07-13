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
  final local = value.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${local.month}-${two(local.day)} ${two(local.hour)}:${two(local.minute)}';
}
