import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import '../app/app_settings.dart';
import 'models.dart';

abstract class Repository {
  Future<DashboardStats> getDashboardStats();
  Future<RobotStatus> getRobotStatus({required String robotId});
  Future<List<AlarmEvent>> listAlarms({
    AlarmType? type,
    RiskLevel? risk,
    AlarmStatus? status,
  });
  Future<AlarmEvent?> getAlarmById(String id);
  Future<AlarmEvent> markAlarmHandled({
    required String id,
    required String remark,
  });

  Future<List<Waypoint>> listWaypoints();
  Future<List<PatrolRoute>> listRoutes();
  Future<void> upsertWaypoint(Waypoint waypoint);
  Future<void> deleteWaypoint(String id);
  Future<void> upsertRoute(PatrolRoute route);
  Future<void> deleteRoute(String id);

  Future<void> sendNavGoal({required MapPoint goal});
  Future<void> setRobotMode({required String robotId, required RobotMode mode});
  Future<void> sendForward({
    required double speedMps,
    double durationSeconds = 3.0,
  });
  Future<void> sendBackward();
  Future<void> sendLeft();
  Future<void> sendRight();
  Future<void> rotateLeft();
  Future<void> rotateRight();
  Future<void> brakeRobot();
  Future<void> sendVectorMotion({required double x, required double y});
  Future<void> takePhoto();
  Future<void> startRecording();
  Future<void> stopRecording();
  Future<void> startTracking();
  Future<void> stopTracking();
  Future<void> updateWheelSpeeds({
    required double leftFront,
    required double leftRear,
    required double rightFront,
    required double rightRear,
  });
  Future<void> stopRobot();

  Future<String> chat(String prompt);
}

class TcpCarRepository extends MockRepository {
  final AppSettings settings;

  TcpCarRepository({required this.settings});

  @override
  Future<void> sendForward({
    required double speedMps,
    double durationSeconds = 3.0,
  }) async {
    await _sendButtonCommand(_CarDirection.front);
  }

  @override
  Future<void> sendBackward() async {
    await _sendButtonCommand(_CarDirection.after);
  }

  @override
  Future<void> sendLeft() async {
    await _sendButtonCommand(_CarDirection.left);
  }

  @override
  Future<void> sendRight() async {
    await _sendButtonCommand(_CarDirection.right);
  }

  @override
  Future<void> rotateLeft() async {
    await _sendButtonCommand(_CarDirection.leftRotate);
  }

  @override
  Future<void> rotateRight() async {
    await _sendButtonCommand(_CarDirection.rightRotate);
  }

  @override
  Future<void> brakeRobot() async {
    await _sendButtonCommand(_CarDirection.brake);
  }

  @override
  Future<void> stopRobot() async {
    await _sendButtonCommand(_CarDirection.stop);
  }

  @override
  Future<void> sendVectorMotion({required double x, required double y}) async {
    final speedX = (x.clamp(-1.0, 1.0) * 100).round();
    final speedY = (y.clamp(-1.0, 1.0) * 100).round();
    await _send(
        _encode('10', [_signedByteHex(speedX), _signedByteHex(speedY)]));
  }

  @override
  Future<void> takePhoto() async {
    await _send(_encode('60', []));
  }

  @override
  Future<void> startRecording() async {
    await _send(_encode('61', []));
  }

  @override
  Future<void> stopRecording() async {
    await _send(_encode('62', []));
  }

  @override
  Future<void> startTracking() async {
    await _send(_encode('63', []));
  }

  @override
  Future<void> stopTracking() async {
    await _send(_encode('64', []));
  }

  @override
  Future<void> updateWheelSpeeds({
    required double leftFront,
    required double leftRear,
    required double rightFront,
    required double rightRear,
  }) async {
    await _send(
      _encode('21', [
        _signedByteHex((leftFront.clamp(-1.0, 1.0) * 100).round()),
        _signedByteHex((leftRear.clamp(-1.0, 1.0) * 100).round()),
        _signedByteHex((rightFront.clamp(-1.0, 1.0) * 100).round()),
        _signedByteHex((rightRear.clamp(-1.0, 1.0) * 100).round()),
      ]),
    );
  }

  Future<void> _sendButtonCommand(_CarDirection direction) async {
    await _send(_encode('15', [_byteHex(direction.value)]));
  }

  Future<void> _send(String message) async {
    Socket? socket;
    try {
      socket = await Socket.connect(
        settings.tcpHost,
        settings.tcpPort,
        timeout: const Duration(seconds: 2),
      );
      socket.add(ascii.encode(message));
      await socket.flush().timeout(const Duration(seconds: 2));
    } on SocketException catch (e) {
      throw StateError(
        'Cannot connect to car TCP ${settings.tcpHost}:${settings.tcpPort}: ${e.message}',
      );
    } on TimeoutException {
      throw TimeoutException(
        'TCP command timed out: ${settings.tcpHost}:${settings.tcpPort}',
      );
    } finally {
      socket?.destroy();
    }
  }

  String _encode(String command, List<String> dataParts) {
    final info = dataParts.join();
    final size = _byteHex(info.length + 2);
    var code = '01$command$size$info';
    code += _byteHex(_checksum(code));
    return '\$$code#';
  }

  int _checksum(String data) {
    var sum = 0;
    for (var i = 0; i < data.length; i += 2) {
      sum = (sum + int.parse(data.substring(i, i + 2), radix: 16)) % 256;
    }
    return sum;
  }

  String _signedByteHex(int value) {
    final normalized = value < 0 ? value + 256 : value;
    return _byteHex(normalized);
  }

  String _byteHex(int value) {
    return value.toRadixString(16).padLeft(2, '0').toUpperCase();
  }
}

enum _CarDirection {
  stop(0),
  front(1),
  after(2),
  left(3),
  right(4),
  leftRotate(5),
  rightRotate(6),
  brake(7);

  final int value;

  const _CarDirection(this.value);
}

class MockRepository implements Repository {
  final _rng = Random(7);

  final List<AlarmEvent> _alarms = [];
  final List<Waypoint> _waypoints = [];
  final List<PatrolRoute> _routes = [];

  MockRepository() {
    _seed();
  }

  void _seed() {
    _waypoints.addAll([
      const Waypoint(
        id: 'wp_1',
        name: '入口',
        point: MapPoint(x: 2.5, y: 1.1, yaw: 0),
      ),
      const Waypoint(
        id: 'wp_2',
        name: '停车区 A',
        point: MapPoint(x: 10.2, y: 3.4, yaw: 1.57),
      ),
      const Waypoint(
        id: 'wp_3',
        name: '地下通道',
        point: MapPoint(x: 6.6, y: 9.8, yaw: 3.14),
      ),
    ]);

    _routes.addAll([
      const PatrolRoute(
        id: 'rt_1',
        name: '默认巡检路线',
        waypointIds: ['wp_1', 'wp_3', 'wp_2'],
      ),
    ]);

    for (var i = 0; i < 18; i++) {
      final type = AlarmType.values[i % AlarmType.values.length];
      final risk = RiskLevel.values[_rng.nextInt(RiskLevel.values.length)];
      final status = i % 4 == 0 ? AlarmStatus.handled : AlarmStatus.unhandled;
      _alarms.add(
        AlarmEvent(
          id: 'al_${i + 1}',
          type: type,
          risk: risk,
          status: status,
          confidence: 0.6 + _rng.nextDouble() * 0.39,
          timestamp: DateTime.now().subtract(Duration(minutes: i * 17)),
          point: MapPoint(
            x: _rng.nextDouble() * 12,
            y: _rng.nextDouble() * 12,
            yaw: _rng.nextDouble() * pi,
          ),
          imagePath: 'assets/mock_alarm.png',
          remark: status == AlarmStatus.handled ? '已安排清理/复检' : null,
        ),
      );
    }
  }

  Future<T> _delay<T>(T value) async {
    await Future<void>.delayed(const Duration(milliseconds: 220));
    return value;
  }

  @override
  Future<DashboardStats> getDashboardStats() async {
    final online = 1 + _rng.nextInt(3);
    final today = 3 + _rng.nextInt(10);
    final high = _alarms
        .where(
          (a) => a.risk == RiskLevel.high && a.status == AlarmStatus.unhandled,
        )
        .length;
    final counts = <AlarmType, int>{};
    for (final t in AlarmType.values) {
      counts[t] = _alarms.where((a) => a.type == t).length;
    }
    return _delay(
      DashboardStats(
        onlineRobots: online,
        todayPatrolCount: today,
        highRiskAlarmCount: high,
        alarmTypeCounts: counts,
      ),
    );
  }

  @override
  Future<RobotStatus> getRobotStatus({required String robotId}) async {
    final mode = RobotMode.values[_rng.nextInt(RobotMode.values.length)];
    final battery = 32 + _rng.nextInt(66);
    final latency = 40 + _rng.nextInt(120);
    final speed = (_rng.nextDouble() * 0.8);
    return _delay(
      RobotStatus(
        robotId: robotId,
        batteryPercent: battery,
        network: NetworkStatus.online,
        mode: mode,
        speedMps: double.parse(speed.toStringAsFixed(2)),
        latencyMs: latency,
      ),
    );
  }

  @override
  Future<List<AlarmEvent>> listAlarms({
    AlarmType? type,
    RiskLevel? risk,
    AlarmStatus? status,
  }) async {
    Iterable<AlarmEvent> q = _alarms;
    if (type != null) q = q.where((a) => a.type == type);
    if (risk != null) q = q.where((a) => a.risk == risk);
    if (status != null) q = q.where((a) => a.status == status);
    final list = q.toList()..sort((a, b) => b.timestamp.compareTo(a.timestamp));
    return _delay(list);
  }

  @override
  Future<AlarmEvent?> getAlarmById(String id) async {
    final a = _alarms.where((e) => e.id == id).toList();
    return _delay(a.isEmpty ? null : a.first);
  }

  @override
  Future<AlarmEvent> markAlarmHandled({
    required String id,
    required String remark,
  }) async {
    final idx = _alarms.indexWhere((e) => e.id == id);
    if (idx < 0) {
      throw StateError('Alarm not found: $id');
    }
    final updated = _alarms[idx].copyWith(
      status: AlarmStatus.handled,
      remark: remark.trim(),
    );
    _alarms[idx] = updated;
    return _delay(updated);
  }

  @override
  Future<List<Waypoint>> listWaypoints() async {
    return _delay(List<Waypoint>.unmodifiable(_waypoints));
  }

  @override
  Future<List<PatrolRoute>> listRoutes() async {
    return _delay(List<PatrolRoute>.unmodifiable(_routes));
  }

  @override
  Future<void> upsertWaypoint(Waypoint waypoint) async {
    final idx = _waypoints.indexWhere((w) => w.id == waypoint.id);
    if (idx < 0) {
      _waypoints.add(waypoint);
    } else {
      _waypoints[idx] = waypoint;
    }
    await _delay(null);
  }

  @override
  Future<void> deleteWaypoint(String id) async {
    _waypoints.removeWhere((w) => w.id == id);
    for (var i = 0; i < _routes.length; i++) {
      final r = _routes[i];
      _routes[i] = PatrolRoute(
        id: r.id,
        name: r.name,
        waypointIds: r.waypointIds.where((wid) => wid != id).toList(),
      );
    }
    await _delay(null);
  }

  @override
  Future<void> upsertRoute(PatrolRoute route) async {
    final idx = _routes.indexWhere((r) => r.id == route.id);
    if (idx < 0) {
      _routes.add(route);
    } else {
      _routes[idx] = route;
    }
    await _delay(null);
  }

  @override
  Future<void> deleteRoute(String id) async {
    _routes.removeWhere((r) => r.id == id);
    await _delay(null);
  }

  @override
  Future<void> sendNavGoal({required MapPoint goal}) async {
    await _delay(null);
  }

  @override
  Future<void> setRobotMode({
    required String robotId,
    required RobotMode mode,
  }) async {
    await _delay(null);
  }

  @override
  Future<void> sendForward({
    required double speedMps,
    double durationSeconds = 3.0,
  }) async {
    await _delay(null);
  }

  @override
  Future<void> sendBackward() async {
    await _delay(null);
  }

  @override
  Future<void> sendLeft() async {
    await _delay(null);
  }

  @override
  Future<void> sendRight() async {
    await _delay(null);
  }

  @override
  Future<void> rotateLeft() async {
    await _delay(null);
  }

  @override
  Future<void> rotateRight() async {
    await _delay(null);
  }

  @override
  Future<void> brakeRobot() async {
    await _delay(null);
  }

  @override
  Future<void> sendVectorMotion({required double x, required double y}) async {
    await _delay(null);
  }

  @override
  Future<void> takePhoto() async {
    await _delay(null);
  }

  @override
  Future<void> startRecording() async {
    await _delay(null);
  }

  @override
  Future<void> stopRecording() async {
    await _delay(null);
  }

  @override
  Future<void> startTracking() async {
    await _delay(null);
  }

  @override
  Future<void> stopTracking() async {
    await _delay(null);
  }

  @override
  Future<void> updateWheelSpeeds({
    required double leftFront,
    required double leftRear,
    required double rightFront,
    required double rightRear,
  }) async {
    await _delay(null);
  }

  @override
  Future<void> stopRobot() async {
    await _delay(null);
  }

  @override
  Future<String> chat(String prompt) async {
    final trimmed = prompt.trim();
    if (trimmed.isEmpty) return _delay('请输入要查询的问题。');
    final total = _alarms.length;
    final unhandled =
        _alarms.where((a) => a.status == AlarmStatus.unhandled).length;
    final high = _alarms
        .where(
          (a) => a.risk == RiskLevel.high && a.status == AlarmStatus.unhandled,
        )
        .length;
    final reply = [
      '已收到：$trimmed',
      'Mock 总结：当前共 $total 条告警，未处理 $unhandled 条，其中高危 $high 条。',
      '后续可接入后端网关：根据区域/时间筛选告警，并生成巡检报告。',
    ].join('\n');
    return _delay(reply);
  }
}
