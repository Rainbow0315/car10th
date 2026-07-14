import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;

import '../app/app_settings.dart';
import 'models.dart';

enum RobotLightEffect {
  off(0),
  running(1),
  marquee(2),
  breathing(3),
  gradient(4),
  starlight(5);

  final int code;

  const RobotLightEffect(this.code);
}

abstract class Repository {
  String cameraSnapshotUrl({
    String topicName = '/image_raw',
    int? cacheBust,
    String? baseUrl,
  });
  String cameraMjpegUrl({
    String topicName = '/image_raw',
    double fps = 5.0,
    String? baseUrl,
  });

  Future<DashboardStats> getDashboardStats();
  Future<RobotStatus> getRobotStatus({required String robotId});
  Future<InspectionMonitorStatus> getInspectionMonitorStatus({
    String? baseUrl,
  });
  Future<InspectionMonitorStatus> startInspectionMonitor({
    String topicName = '/image_raw',
    String robotCode = 'robot_001',
    String cameraCode = 'usb_cam',
    List<String> enabledModels = const ['crack', 'puddle', 'fod'],
    String? baseUrl,
  });
  Future<InspectionMonitorStatus> stopInspectionMonitor({
    String? baseUrl,
  });
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
  Future<SlamMap> getSlamMap();

  Future<void> setInitialPose({required MapPoint pose});
  Future<void> sendNavGoal({required MapPoint goal});
  Future<void> setRobotMode({required String robotId, required RobotMode mode});
  Future<void> sendFleetForward({
    required List<String> robotCodes,
    double speedMps = 0.12,
    double durationSeconds = 5.0,
  });
  Future<void> sendFleetVelocity({
    required List<String> robotCodes,
    required double linearX,
    required double linearY,
    required double angularZ,
    double durationSeconds = 0.35,
    double rateHz = 10.0,
  });
  Future<void> sendFleetVectorMotion({
    required List<String> robotCodes,
    required double x,
    required double y,
  });
  Future<void> stopFleetRobots({required List<String> robotCodes});
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
  Future<void> startFleetTracking({required List<String> robotCodes});
  Future<void> stopFleetTracking({required List<String> robotCodes});
  Future<void> setLightEffect(RobotLightEffect effect);
  Future<void> startLightShow();
  Future<void> stopLightShow();
  Future<void> playAudio();
  Future<void> updateWheelSpeeds({
    required double leftFront,
    required double leftRear,
    required double rightFront,
    required double rightRear,
  });
  Future<void> stopRobot();

  Future<String> chat(String prompt);
  Future<LlmRuntimeStatus> getLlmRuntimeStatus();
  Future<LlmTaskPlan> planLlmTask(String prompt);
  Future<LlmTaskPlan> executeLlmTask({
    required String planId,
    required bool confirmed,
  });

  void dispose() {}
}

class TcpCarRepository extends MockRepository {
  static const _connectTimeout = Duration(seconds: 2);
  static const _sendTimeout = Duration(seconds: 2);

  final AppSettings settings;
  Socket? _socket;
  String? _socketHost;
  int? _socketPort;
  Future<void> _sendChain = Future.value();
  bool _disposed = false;

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
      _encode('10', [_signedByteHex(speedX), _signedByteHex(speedY)]),
    );
  }

  @override
  Future<void> sendFleetVectorMotion({
    required List<String> robotCodes,
    required double x,
    required double y,
  }) async {
    final speedX = (x.clamp(-1.0, 1.0) * 100).round();
    final speedY = (y.clamp(-1.0, 1.0) * 100).round();
    final message = _encode(
      '10',
      [_signedByteHex(speedX), _signedByteHex(speedY)],
    );
    await _sendFleetRaw(robotCodes, message);
  }

  @override
  Future<void> sendFleetVelocity({
    required List<String> robotCodes,
    required double linearX,
    required double linearY,
    required double angularZ,
    double durationSeconds = 0.35,
    double rateHz = 10.0,
  }) async {
    final direction = _directionFromVelocity(
      linearX: linearX,
      linearY: linearY,
      angularZ: angularZ,
    );
    await _sendFleetRaw(
      robotCodes,
      _encode('15', [_byteHex(direction.value)]),
    );
  }

  @override
  Future<void> stopFleetRobots({required List<String> robotCodes}) async {
    await _sendFleetRaw(
      robotCodes,
      _encode('15', [_byteHex(_CarDirection.stop.value)]),
    );
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
  Future<void> startFleetTracking({required List<String> robotCodes}) async {
    await _sendFleetRaw(robotCodes, _encode('63', []));
  }

  @override
  Future<void> stopFleetTracking({required List<String> robotCodes}) async {
    await _sendFleetRaw(robotCodes, _encode('64', []));
  }

  @override
  Future<void> setLightEffect(RobotLightEffect effect) async {
    await _send(_encode('30', [_byteHex(effect.code)]));
  }

  @override
  Future<void> startLightShow() async {
    await _send(_encode('31', []));
  }

  @override
  Future<void> stopLightShow() async {
    await _send(_encode('32', []));
  }

  @override
  Future<void> playAudio() async {
    await _send(_encode('33', []));
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

  Future<void> _send(String message) {
    if (_disposed) {
      throw StateError('TCP car repository has been disposed');
    }
    final pending = _sendChain.then(
      (_) => _sendLocked(settings.tcpHost, settings.tcpPort, message),
    );
    _sendChain = pending.catchError((_) {});
    return pending;
  }

  Future<void> _sendFleetRaw(List<String> robotCodes, String message) async {
    if (_disposed) {
      throw StateError('TCP car repository has been disposed');
    }
    final codes = robotCodes.isEmpty ? [settings.controlRobotCode] : robotCodes;
    Future<void> pending = _sendChain;
    for (final code in codes) {
      final target = _controlTargetFor(code);
      pending = pending.then(
        (_) => _sendLocked(target.host, target.tcpPort, message),
      );
    }
    _sendChain = pending.catchError((_) {});
    return pending;
  }

  Future<void> _sendLocked(String host, int port, String message) async {
    try {
      final socket = await _ensureSocket(host, port);
      socket.add(ascii.encode(message));
      await socket.flush().timeout(_sendTimeout);
    } on SocketException catch (e) {
      _dropSocket();
      throw StateError(
        'Cannot connect to car TCP $host:$port: ${e.message}',
      );
    } on TimeoutException {
      _dropSocket();
      throw TimeoutException(
        'TCP command timed out: $host:$port',
      );
    }
  }

  Future<Socket> _ensureSocket(String host, int port) async {
    final current = _socket;
    if (current != null && _socketHost == host && _socketPort == port) {
      return current;
    }

    _dropSocket();
    final socket = await Socket.connect(host, port, timeout: _connectTimeout);
    socket.setOption(SocketOption.tcpNoDelay, true);
    _socket = socket;
    _socketHost = host;
    _socketPort = port;
    unawaited(
      socket.done.catchError((_) {}).whenComplete(() {
        if (identical(_socket, socket)) {
          _socket = null;
          _socketHost = null;
          _socketPort = null;
        }
      }),
    );
    return socket;
  }

  RobotControlTarget _controlTargetFor(String code) {
    return settings.controlTargets.firstWhere(
      (target) => target.code == code,
      orElse: () => settings.selectedControlTarget,
    );
  }

  _CarDirection _directionFromVelocity({
    required double linearX,
    required double linearY,
    required double angularZ,
  }) {
    final ax = linearX.abs();
    final ay = linearY.abs();
    final az = angularZ.abs();
    if (ax < 0.001 && ay < 0.001 && az < 0.001) {
      return _CarDirection.stop;
    }
    if (az >= ax && az >= ay) {
      return angularZ > 0
          ? _CarDirection.leftRotate
          : _CarDirection.rightRotate;
    }
    if (ax >= ay) {
      return linearX > 0 ? _CarDirection.front : _CarDirection.after;
    }
    return linearY > 0 ? _CarDirection.left : _CarDirection.right;
  }

  void _dropSocket() {
    final socket = _socket;
    _socket = null;
    _socketHost = null;
    _socketPort = null;
    socket?.destroy();
  }

  @override
  void dispose() {
    _disposed = true;
    _dropSocket();
    super.dispose();
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

class CloudRepository extends TcpCarRepository {
  CloudRepository({required super.settings});

  Uri _uri(
    String path, {
    Map<String, String?> query = const {},
    String? baseUrl,
  }) {
    final base =
        (baseUrl ?? settings.apiBaseUrl).replaceAll(RegExp(r'/+$'), '');
    final cleanPath = path.startsWith('/') ? path : '/$path';
    final params = <String, String>{};
    for (final entry in query.entries) {
      final value = entry.value;
      if (value != null && value.isNotEmpty) params[entry.key] = value;
    }
    return Uri.parse(
      '$base$cleanPath',
    ).replace(queryParameters: params.isEmpty ? null : params);
  }

  @override
  String cameraSnapshotUrl({
    String topicName = '/image_raw',
    int? cacheBust,
    String? baseUrl,
  }) {
    return _uri(
      '/api/inspection/camera/snapshot',
      query: {
        'topic_name': topicName,
        'timeout_sec': '3.0',
        if (cacheBust != null) 't': cacheBust.toString(),
      },
      baseUrl: baseUrl,
    ).toString();
  }

  @override
  String cameraMjpegUrl({
    String topicName = '/image_raw',
    double fps = 5.0,
    String? baseUrl,
  }) {
    return _uri(
      '/api/inspection/camera/mjpeg',
      query: {
        'topic_name': topicName,
        'fps': fps.toStringAsFixed(1),
        'timeout_sec': '3.0',
      },
      baseUrl: baseUrl,
    ).toString();
  }

  Future<dynamic> _getJson(
    String path, {
    Map<String, String?> query = const {},
    String? baseUrl,
  }) async {
    final response = await http
        .get(_uri(path, query: query, baseUrl: baseUrl))
        .timeout(const Duration(seconds: 10));
    return _decode(response);
  }

  Future<dynamic> _postJson(
    String path,
    Map<String, Object?> body, {
    String? baseUrl,
  }) async {
    final response = await http
        .post(
          _uri(path, baseUrl: baseUrl),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 30));
    return _decode(response);
  }

  dynamic _decode(http.Response response) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError('HTTP ${response.statusCode}: ${response.body}');
    }
    if (response.body.isEmpty) return null;
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  @override
  Future<InspectionMonitorStatus> getInspectionMonitorStatus({
    String? baseUrl,
  }) async {
    final json = await _getJson(
      '/api/inspection/monitor/status',
      baseUrl: baseUrl,
    ) as Map<String, dynamic>;
    return _monitorFromJson(json);
  }

  @override
  Future<String> chat(String prompt) async {
    final plan = await planLlmTask(prompt);
    return plan.assistantMessage;
  }

  @override
  Future<LlmRuntimeStatus> getLlmRuntimeStatus() async {
    final json = await _getJson(
      '/api/llm/status',
      baseUrl: settings.llmApiBaseUrl,
    ) as Map<String, dynamic>;
    return _llmRuntimeStatusFromJson(json);
  }

  @override
  Future<LlmTaskPlan> planLlmTask(String prompt) async {
    final robotCode = settings.controlRobotCode.startsWith('robot_')
        ? settings.controlRobotCode
        : 'robot_001';
    final json = await _postJson(
      '/api/llm/tasks/plan',
      {
        'message': prompt,
        'robot_codes': [robotCode],
        'allow_llm': true,
        'auto_execute': false,
      },
      baseUrl: settings.llmApiBaseUrl,
    ) as Map<String, dynamic>;
    return _llmPlanFromJson(json);
  }

  @override
  Future<LlmTaskPlan> executeLlmTask({
    required String planId,
    required bool confirmed,
  }) async {
    final json = await _postJson(
      '/api/llm/tasks/$planId/execute',
      {
        'confirmed': confirmed,
      },
      baseUrl: settings.llmApiBaseUrl,
    ) as Map<String, dynamic>;
    final steps = (json['steps'] as List? ?? const [])
        .map(
          (item) => _llmStepFromJson((item as Map).cast<String, dynamic>()),
        )
        .toList();
    return LlmTaskPlan(
      planId: json['plan_id']?.toString() ?? planId,
      assistantMessage: '任务已执行，下面是后端返回的真实执行结果。',
      source: 'backend',
      requiresConfirmation: false,
      safetyNotes: (json['safety_notes'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      steps: steps,
    );
  }

  @override
  Future<InspectionMonitorStatus> startInspectionMonitor({
    String topicName = '/image_raw',
    String robotCode = 'robot_001',
    String cameraCode = 'usb_cam',
    List<String> enabledModels = const ['crack', 'puddle', 'fod'],
    String? baseUrl,
  }) async {
    final json = await _postJson(
        '/api/inspection/monitor/start',
        {
          'topic_name': topicName,
          'interval_sec': 1.0,
          'timeout_sec': 10.0,
          'robot_code': robotCode,
          'camera_code': cameraCode,
          'enabled_models': enabledModels,
        },
        baseUrl: baseUrl) as Map<String, dynamic>;
    return _monitorFromJson(json);
  }

  @override
  Future<InspectionMonitorStatus> stopInspectionMonitor({
    String? baseUrl,
  }) async {
    final json = await _postJson(
      '/api/inspection/monitor/stop',
      <String, Object?>{},
      baseUrl: baseUrl,
    ) as Map<String, dynamic>;
    return _monitorFromJson(json);
  }

  @override
  Future<DashboardStats> getDashboardStats() async {
    final alarms = await listAlarms();
    var onlineRobots = 0;
    var todayPatrolCount = 0;
    try {
      final summary =
          await _getJson('/api/fleet/summary') as Map<String, dynamic>;
      onlineRobots = _asInt(summary['online_robots']);
      todayPatrolCount = _asInt(summary['acked_commands']);
    } catch (_) {
      try {
        final robot = await getRobotStatus(robotId: 'robot_001');
        onlineRobots = robot.network == NetworkStatus.online ? 1 : 0;
      } catch (_) {
        onlineRobots = 0;
      }
    }

    final counts = <AlarmType, int>{};
    for (final t in AlarmType.values) {
      counts[t] = alarms.where((a) => a.type == t).length;
    }
    final high = alarms
        .where(
          (a) => a.risk == RiskLevel.high && a.status == AlarmStatus.unhandled,
        )
        .length;
    return DashboardStats(
      onlineRobots: onlineRobots,
      todayPatrolCount: todayPatrolCount,
      highRiskAlarmCount: high,
      alarmTypeCounts: counts,
    );
  }

  @override
  Future<RobotStatus> getRobotStatus({required String robotId}) async {
    final code = robotId == 'robot_01' ? 'robot_001' : robotId;
    final json =
        await _getJson('/api/fleet/robots/$code') as Map<String, dynamic>;
    final payload =
        (json['payload'] as Map?)?.cast<String, dynamic>() ?? const {};
    return RobotStatus(
      robotId: (json['robot_code'] ?? code).toString(),
      batteryPercent: _asInt(json['battery']),
      network: json['status'] == 'online'
          ? NetworkStatus.online
          : NetworkStatus.offline,
      mode: _robotModeFromApi((json['mode'] ?? payload['mode']).toString()),
      speedMps: _asDouble(payload['speed_mps'] ?? payload['linear_x']),
      latencyMs: _asInt(json['network_latency']),
    );
  }

  @override
  Future<SlamMap> getSlamMap() async {
    final json = await _getJson('/api/slam/map') as Map<String, dynamic>;
    return _slamMapFromJson(json);
  }

  @override
  Future<void> setInitialPose({required MapPoint pose}) async {
    await _postJson('/api/slam/initial-pose', {
      'x': pose.x,
      'y': pose.y,
      'yaw': pose.yaw,
      'frame_id': 'map',
    });
  }

  @override
  Future<void> sendNavGoal({required MapPoint goal}) async {
    await _postJson('/api/slam/goal', {
      'x': goal.x,
      'y': goal.y,
      'yaw': goal.yaw,
      'frame_id': 'map',
    });
  }

  @override
  Future<void> sendFleetForward({
    required List<String> robotCodes,
    double speedMps = 0.12,
    double durationSeconds = 5.0,
  }) async {
    await sendFleetVelocity(
      robotCodes: robotCodes,
      linearX: speedMps,
      linearY: 0.0,
      angularZ: 0.0,
      durationSeconds: durationSeconds,
    );
  }

  @override
  Future<void> sendFleetVelocity({
    required List<String> robotCodes,
    required double linearX,
    required double linearY,
    required double angularZ,
    double durationSeconds = 0.35,
    double rateHz = 10.0,
  }) async {
    await super.sendFleetVelocity(
      robotCodes: robotCodes,
      linearX: linearX,
      linearY: linearY,
      angularZ: angularZ,
      durationSeconds: durationSeconds,
      rateHz: rateHz,
    );
  }

  @override
  Future<void> stopFleetRobots({required List<String> robotCodes}) async {
    await super.stopFleetRobots(robotCodes: robotCodes);
  }

  @override
  Future<List<AlarmEvent>> listAlarms({
    AlarmType? type,
    RiskLevel? risk,
    AlarmStatus? status,
  }) async {
    final json = await _getJson(
      '/api/inspection/alarms',
      query: {
        'limit': '100',
        'alarm_type': type == null ? null : _alarmTypeToApi(type),
        'risk_level': risk == null ? null : _riskToApi(risk),
        'status': status == null ? null : _statusToApi(status),
      },
    ) as Map<String, dynamic>;
    final items = (json['items'] as List? ?? const []);
    return items
        .map((item) => _alarmFromJson((item as Map).cast<String, dynamic>()))
        .toList();
  }

  @override
  Future<AlarmEvent?> getAlarmById(String id) async {
    try {
      final json =
          await _getJson('/api/inspection/alarms/$id') as Map<String, dynamic>;
      return _alarmFromJson(json);
    } catch (_) {
      return null;
    }
  }

  @override
  Future<AlarmEvent> markAlarmHandled({
    required String id,
    required String remark,
  }) async {
    final json =
        await _postJson('/api/inspection/alarms/$id/handle', {'remark': remark})
            as Map<String, dynamic>;
    return _alarmFromJson(json);
  }

  InspectionMonitorStatus _monitorFromJson(Map<String, dynamic> json) {
    return InspectionMonitorStatus(
      running: json['running'] == true,
      topicName: (json['topic_name'] ?? '/image_raw').toString(),
      intervalSec: _asDouble(json['interval_sec']),
      totalFrames: _asInt(json['total_frames']),
      totalAlarmFrames: _asInt(json['total_alarm_frames']),
      totalAlarms: _asInt(json['total_alarms']),
      startedAt: _parseDate(json['started_at']),
      lastCheckedAt: _parseDate(json['last_checked_at']),
      lastAlarmAt: _parseDate(json['last_alarm_at']),
      lastError: json['last_error']?.toString(),
    );
  }

  LlmTaskPlan _llmPlanFromJson(Map<String, dynamic> json) {
    return LlmTaskPlan(
      planId: json['plan_id']?.toString() ?? '',
      assistantMessage: json['assistant_message']?.toString() ?? '',
      source: json['source']?.toString() ?? 'rule_fallback',
      requiresConfirmation: json['requires_confirmation'] == true,
      safetyNotes: (json['safety_notes'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      steps: (json['steps'] as List? ?? const [])
          .map(
            (item) => _llmStepFromJson((item as Map).cast<String, dynamic>()),
          )
          .toList(),
    );
  }

  LlmRuntimeStatus _llmRuntimeStatusFromJson(Map<String, dynamic> json) {
    return LlmRuntimeStatus(
      llmConfigured: json['llm_configured'] == true,
      apiBaseHost: json['api_base_host']?.toString(),
      model: json['model']?.toString() ?? '',
      plannerMode: json['planner_mode']?.toString() ?? 'rule_fallback',
      message: json['message']?.toString() ?? '',
    );
  }

  LlmPlanStep _llmStepFromJson(Map<String, dynamic> json) {
    final result = json['result'];
    return LlmPlanStep(
      stepId: json['step_id']?.toString() ?? '',
      tool: json['tool']?.toString() ?? '',
      title: json['title']?.toString() ?? '',
      safetyLevel: json['safety_level']?.toString() ?? 'read_only',
      requiresConfirmation: json['requires_confirmation'] == true,
      status: json['status']?.toString() ?? 'planned',
      arguments:
          (json['arguments'] as Map? ?? const {}).cast<String, Object?>(),
      result: result is Map ? result.cast<String, Object?>() : null,
      error: json['error']?.toString(),
    );
  }

  AlarmEvent _alarmFromJson(Map<String, dynamic> json) {
    final id = (json['alarm_no'] ?? json['id']).toString();
    final imageUrl = json['image_url']?.toString();
    return AlarmEvent(
      id: id,
      type: _alarmTypeFromApi((json['alarm_type'] ?? '').toString()),
      risk: _riskFromApi((json['risk_level'] ?? '').toString()),
      status: _statusFromApi((json['status'] ?? '').toString()),
      confidence: _asDouble(json['confidence']),
      timestamp: _parseDate(json['detected_at']) ?? DateTime.now(),
      point: MapPoint(
        x: _asDouble(json['pos_x']),
        y: _asDouble(json['pos_y']),
        yaw: _asDouble(json['pos_yaw']),
      ),
      imagePath: imageUrl?.isNotEmpty == true
          ? imageUrl!
          : _uri('/api/inspection/alarms/$id/image').toString(),
      robotCode: json['robot_code']?.toString(),
      cameraCode: json['camera_code']?.toString(),
      detectionModel: json['detection_model']?.toString(),
      detectionLabel: json['detection_label']?.toString(),
      bbox:
          (json['bbox'] as List? ?? const []).map((e) => _asDouble(e)).toList(),
      remark: json['handle_remark']?.toString(),
    );
  }

  AlarmType _alarmTypeFromApi(String value) {
    switch (value) {
      case 'water':
        return AlarmType.water;
      case 'crack':
        return AlarmType.crack;
      case 'foreign_object':
      case 'fod':
        return AlarmType.debris;
      default:
        return AlarmType.debris;
    }
  }

  String _alarmTypeToApi(AlarmType type) {
    switch (type) {
      case AlarmType.water:
        return 'water';
      case AlarmType.crack:
        return 'crack';
      case AlarmType.debris:
        return 'foreign_object';
      case AlarmType.smoking:
        return 'other';
    }
  }

  RiskLevel _riskFromApi(String value) {
    switch (value) {
      case 'high':
        return RiskLevel.high;
      case 'medium':
        return RiskLevel.medium;
      default:
        return RiskLevel.low;
    }
  }

  String _riskToApi(RiskLevel risk) => risk.name;

  AlarmStatus _statusFromApi(String value) {
    return value == 'closed' ? AlarmStatus.handled : AlarmStatus.unhandled;
  }

  String _statusToApi(AlarmStatus status) {
    return status == AlarmStatus.handled ? 'closed' : 'pending';
  }

  RobotMode _robotModeFromApi(String value) {
    switch (value) {
      case 'patrol':
        return RobotMode.patrol;
      case 'follow':
        return RobotMode.follow;
      default:
        return RobotMode.standby;
    }
  }

  SlamMap _slamMapFromJson(Map<String, dynamic> json) {
    final origin =
        (json['origin'] as Map?)?.cast<String, dynamic>() ?? const {};
    final pose = (json['robot_pose'] as Map?)?.cast<String, dynamic>();
    return SlamMap(
      available: json['available'] == true,
      frameId: json['frame_id']?.toString(),
      width: _asInt(json['width']),
      height: _asInt(json['height']),
      resolution: _asDouble(json['resolution']),
      origin: SlamMapOrigin(
        x: _asDouble(origin['x']),
        y: _asDouble(origin['y']),
        yaw: _asDouble(origin['yaw']),
      ),
      robotPose: pose == null
          ? null
          : MapPoint(
              x: _asDouble(pose['x']),
              y: _asDouble(pose['y']),
              yaw: _asDouble(pose['yaw']),
            ),
      laserPoints: (json['laser_points'] as List? ?? const []).map((item) {
        final point = (item as Map).cast<String, dynamic>();
        return MapPoint(
          x: _asDouble(point['x']),
          y: _asDouble(point['y']),
          yaw: 0,
        );
      }).toList(growable: false),
      data: (json['data'] as List? ?? const [])
          .map((value) => _asInt(value))
          .toList(growable: false),
    );
  }

  DateTime? _parseDate(dynamic value) {
    if (value == null) return null;
    return DateTime.tryParse(value.toString());
  }

  int _asInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.round();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  double _asDouble(dynamic value) {
    if (value is double) return value;
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '') ?? 0.0;
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
  bool _monitorRunning = false;

  MockRepository() {
    _seed();
  }

  @override
  void dispose() {}

  @override
  String cameraSnapshotUrl({
    String topicName = '/image_raw',
    int? cacheBust,
    String? baseUrl,
  }) {
    final seed = cacheBust ?? DateTime.now().millisecondsSinceEpoch;
    return 'https://placehold.co/640x360/png?text=Camera+$seed';
  }

  @override
  String cameraMjpegUrl({
    String topicName = '/image_raw',
    double fps = 5.0,
    String? baseUrl,
  }) {
    return cameraSnapshotUrl(topicName: topicName);
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

    _alarms.clear();
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
  Future<InspectionMonitorStatus> getInspectionMonitorStatus({
    String? baseUrl,
  }) async {
    return _delay(_mockMonitorStatus());
  }

  @override
  Future<InspectionMonitorStatus> startInspectionMonitor({
    String topicName = '/image_raw',
    String robotCode = 'robot_001',
    String cameraCode = 'usb_cam',
    List<String> enabledModels = const ['crack', 'puddle', 'fod'],
    String? baseUrl,
  }) async {
    _monitorRunning = true;
    return _delay(_mockMonitorStatus());
  }

  @override
  Future<InspectionMonitorStatus> stopInspectionMonitor({
    String? baseUrl,
  }) async {
    _monitorRunning = false;
    return _delay(_mockMonitorStatus());
  }

  InspectionMonitorStatus _mockMonitorStatus() {
    return InspectionMonitorStatus(
      running: _monitorRunning,
      topicName: '/image_raw',
      intervalSec: 1,
      totalFrames: _monitorRunning ? 24 : 0,
      totalAlarmFrames: _monitorRunning ? 3 : 0,
      totalAlarms:
          _alarms.where((a) => a.status == AlarmStatus.unhandled).length,
      startedAt: _monitorRunning
          ? DateTime.now().subtract(const Duration(minutes: 3))
          : null,
      lastCheckedAt: _monitorRunning ? DateTime.now() : null,
      lastAlarmAt: _monitorRunning
          ? DateTime.now().subtract(const Duration(seconds: 40))
          : null,
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
  Future<SlamMap> getSlamMap() async {
    const width = 48;
    const height = 36;
    final data = List<int>.filled(width * height, 0);
    for (var x = 0; x < width; x++) {
      data[x] = 100;
      data[(height - 1) * width + x] = 100;
    }
    for (var y = 0; y < height; y++) {
      data[y * width] = 100;
      data[y * width + width - 1] = 100;
    }
    for (var x = 10; x < 34; x++) {
      data[12 * width + x] = 100;
    }
    for (var y = 18; y < 30; y++) {
      data[y * width + 28] = 100;
    }
    return _delay(
      SlamMap(
        available: true,
        frameId: 'map',
        width: width,
        height: height,
        resolution: 0.05,
        origin: const SlamMapOrigin(x: -1.2, y: -0.9, yaw: 0),
        robotPose: const MapPoint(x: 0.2, y: 0.1, yaw: 0.5),
        laserPoints: List<MapPoint>.generate(60, (i) {
          final a = i * pi / 30;
          return MapPoint(x: 0.2 + cos(a) * 0.7, y: 0.1 + sin(a) * 0.7, yaw: 0);
        }),
        data: data,
      ),
    );
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
  Future<void> setInitialPose({required MapPoint pose}) async {
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
  Future<void> sendFleetForward({
    required List<String> robotCodes,
    double speedMps = 0.12,
    double durationSeconds = 5.0,
  }) async {
    await _delay(null);
  }

  @override
  Future<void> sendFleetVelocity({
    required List<String> robotCodes,
    required double linearX,
    required double linearY,
    required double angularZ,
    double durationSeconds = 0.35,
    double rateHz = 10.0,
  }) async {
    await _delay(null);
  }

  @override
  Future<void> sendFleetVectorMotion({
    required List<String> robotCodes,
    required double x,
    required double y,
  }) async {
    await _delay(null);
  }

  @override
  Future<void> stopFleetRobots({required List<String> robotCodes}) async {
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
  Future<void> startFleetTracking({required List<String> robotCodes}) async {
    await _delay(null);
  }

  @override
  Future<void> stopFleetTracking({required List<String> robotCodes}) async {
    await _delay(null);
  }

  @override
  Future<void> setLightEffect(RobotLightEffect effect) async {
    await _delay(null);
  }

  @override
  Future<void> startLightShow() async {
    await _delay(null);
  }

  @override
  Future<void> stopLightShow() async {
    await _delay(null);
  }

  @override
  Future<void> playAudio() async {
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

  @override
  Future<LlmRuntimeStatus> getLlmRuntimeStatus() async {
    return _delay(
      const LlmRuntimeStatus(
        llmConfigured: false,
        model: 'mock',
        plannerMode: 'rule_fallback',
        message: 'Mock 模式：未连接真实 LLM，当前只演示安全规划流程。',
      ),
    );
  }

  @override
  Future<LlmTaskPlan> planLlmTask(String prompt) async {
    final robotCode = prompt.contains('robot_002') ? 'robot_002' : 'robot_001';
    final step = prompt.contains('急停') || prompt.toLowerCase().contains('stop')
        ? LlmPlanStep(
            stepId: 'step_1',
            tool: 'fleet.safety_stop',
            title: '安全停止小车',
            safetyLevel: 'safe_command',
            requiresConfirmation: true,
            status: 'planned',
            arguments: {
              'robot_codes': [robotCode]
            },
          )
        : const LlmPlanStep(
            stepId: 'step_1',
            tool: 'fleet.summary',
            title: '查询车队总览',
            safetyLevel: 'read_only',
            requiresConfirmation: false,
            status: 'planned',
            arguments: {},
          );
    return _delay(
      LlmTaskPlan(
        planId: 'mock_${DateTime.now().millisecondsSinceEpoch}',
        assistantMessage: '已生成安全任务计划，请确认后执行。',
        source: 'mock',
        requiresConfirmation: step.requiresConfirmation,
        safetyNotes: const [
          'LLM 只生成任务计划，后端负责安全校验。',
          '不会允许直接下发任意底盘速度。',
        ],
        steps: [step],
      ),
    );
  }

  @override
  Future<LlmTaskPlan> executeLlmTask({
    required String planId,
    required bool confirmed,
  }) async {
    return _delay(
      LlmTaskPlan(
        planId: planId,
        assistantMessage: 'Mock 执行完成。',
        source: 'mock',
        requiresConfirmation: false,
        safetyNotes: const ['Mock 模式未真实控制小车。'],
        steps: const [
          LlmPlanStep(
            stepId: 'step_1',
            tool: 'mock',
            title: 'Mock 执行结果',
            safetyLevel: 'read_only',
            requiresConfirmation: false,
            status: 'executed',
            arguments: {},
            result: {'status': 'ok'},
          ),
        ],
      ),
    );
  }
}
