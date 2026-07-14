import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AppSettings extends ChangeNotifier {
  static const _kTcpHostKey = 'settings.tcpHost';
  static const _kTcpPortKey = 'settings.tcpPort';
  static const _kControlRobotCodeKey = 'settings.controlRobotCode';
  static const _kApiBaseUrlKey = 'settings.apiBaseUrl';
  static const _kLlmApiBaseUrlKey = 'settings.llmApiBaseUrl';
  static const _defaultTcpHost = '192.168.137.239';
  static const _defaultTcpPort = 6001;
  static const _defaultControlRobotCode = 'robot_001';
  static const _defaultApiBaseUrl = 'http://192.168.137.239:8000';
  static const _defaultLlmApiBaseUrl = 'http://192.168.137.51:8000';
  static const _legacyApiBaseUrls = {
    'http://192.168.137.51:8000',
  };
  static const _legacyTcpHosts = {
    '192.168.137.89': '192.168.137.95',
  };

  String _tcpHost = _defaultTcpHost;
  int _tcpPort = _defaultTcpPort;
  String _controlRobotCode = _defaultControlRobotCode;
  String _apiBaseUrl = _defaultApiBaseUrl;
  String _llmApiBaseUrl = _defaultLlmApiBaseUrl;

  List<RobotControlTarget> get controlTargets => const [
        RobotControlTarget(
          code: 'robot_001',
          label: '小车1',
          host: '192.168.137.239',
          tcpPort: 6001,
          apiBaseUrl: 'http://192.168.137.239:8000',
        ),
        RobotControlTarget(
          code: 'robot_002',
          label: '小车2',
          host: '192.168.137.95',
          tcpPort: 6001,
          apiBaseUrl: 'http://192.168.137.95:8000',
        ),
      ];

  String get tcpHost => _tcpHost;
  int get tcpPort => _tcpPort;
  String get controlRobotCode => _controlRobotCode;
  RobotControlTarget get selectedControlTarget {
    return controlTargets.firstWhere(
      (target) => target.code == _controlRobotCode,
      orElse: () => controlTargets.first,
    );
  }

  String get apiBaseUrl => _apiBaseUrl;
  String get llmApiBaseUrl => _llmApiBaseUrl;

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    final savedControlRobot = prefs.getString(_kControlRobotCodeKey);
    final hasSavedControlRobot = savedControlRobot != null &&
        controlTargets.any((target) => target.code == savedControlRobot);
    if (hasSavedControlRobot) {
      _controlRobotCode = savedControlRobot;
    }

    final savedTcpHost = prefs.getString(_kTcpHostKey);
    _tcpHost = _normalizeTcpHost(savedTcpHost ?? _tcpHost);
    final savedTcpPort = prefs.getInt(_kTcpPortKey);
    _tcpPort = savedTcpPort == null || savedTcpPort == 6000
        ? _defaultTcpPort
        : savedTcpPort;
    if (savedTcpPort == 6000) {
      await prefs.setInt(_kTcpPortKey, _defaultTcpPort);
    }
    if (!hasSavedControlRobot) {
      final inferredTarget = _targetForTcp(_tcpHost, _tcpPort);
      if (inferredTarget != null) {
        _controlRobotCode = inferredTarget.code;
        await prefs.setString(_kControlRobotCodeKey, inferredTarget.code);
      }
    }

    final savedApiBaseUrl = prefs.getString(_kApiBaseUrlKey);
    final savedLlmApiBaseUrl = prefs.getString(_kLlmApiBaseUrlKey);
    _apiBaseUrl = _normalizeApiBaseUrl(savedApiBaseUrl, _controlRobotCode);
    _llmApiBaseUrl = savedLlmApiBaseUrl ?? _llmApiBaseUrl;
    if (!hasSavedControlRobot) {
      final inferredTarget = _targetForApi(_apiBaseUrl);
      if (inferredTarget != null) {
        _controlRobotCode = inferredTarget.code;
        _tcpHost = inferredTarget.host;
        _tcpPort = inferredTarget.tcpPort;
        _apiBaseUrl = inferredTarget.apiBaseUrl;
        await prefs.setString(_kControlRobotCodeKey, inferredTarget.code);
        await prefs.setString(_kTcpHostKey, inferredTarget.host);
        await prefs.setInt(_kTcpPortKey, inferredTarget.tcpPort);
      }
    }

    if (savedTcpHost != null && savedTcpHost != _tcpHost) {
      await prefs.setString(_kTcpHostKey, _tcpHost);
    }
    if (savedApiBaseUrl != _apiBaseUrl) {
      await prefs.setString(_kApiBaseUrlKey, _apiBaseUrl);
    }
    if (savedApiBaseUrl != null && _legacyApiBaseUrls.contains(savedApiBaseUrl)) {
      if (savedLlmApiBaseUrl == null) {
        _llmApiBaseUrl = savedApiBaseUrl;
        await prefs.setString(_kLlmApiBaseUrlKey, _llmApiBaseUrl);
      }
    }
    notifyListeners();
  }

  Future<void> selectControlRobot(String robotCode) async {
    final target = controlTargets.firstWhere(
      (item) => item.code == robotCode,
      orElse: () => selectedControlTarget,
    );
    _controlRobotCode = target.code;
    _tcpHost = target.host;
    _tcpPort = target.tcpPort;
    _apiBaseUrl = target.apiBaseUrl;

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kControlRobotCodeKey, target.code);
    await prefs.setString(_kTcpHostKey, target.host);
    await prefs.setInt(_kTcpPortKey, target.tcpPort);
    await prefs.setString(_kApiBaseUrlKey, target.apiBaseUrl);
    notifyListeners();
  }

  Future<void> updateTcpConnection({
    required String host,
    required String port,
  }) async {
    final cleanHost = host.trim();
    final parsedPort = int.tryParse(port.trim());
    if (cleanHost.isEmpty || parsedPort == null || parsedPort <= 0) return;

    _tcpHost = cleanHost;
    _tcpPort = parsedPort;
    _controlRobotCode = 'custom';
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kControlRobotCodeKey, _controlRobotCode);
    await prefs.setString(_kTcpHostKey, cleanHost);
    await prefs.setInt(_kTcpPortKey, parsedPort);
    notifyListeners();
  }

  Future<void> updateApiBaseUrl(String value) async {
    final clean = value.trim().replaceAll(RegExp(r'/+$'), '');
    if (clean.isEmpty || Uri.tryParse(clean)?.hasScheme != true) return;

    _apiBaseUrl = clean;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kApiBaseUrlKey, clean);
    notifyListeners();
  }

  Future<void> updateLlmApiBaseUrl(String value) async {
    final clean = value.trim().replaceAll(RegExp(r'/+$'), '');
    if (clean.isEmpty || Uri.tryParse(clean)?.hasScheme != true) return;

    _llmApiBaseUrl = clean;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kLlmApiBaseUrlKey, clean);
    notifyListeners();
  }

  Future<void> clearLocalCache() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kTcpHostKey);
    await prefs.remove(_kTcpPortKey);
    await prefs.remove(_kControlRobotCodeKey);
    await prefs.remove(_kApiBaseUrlKey);
    await prefs.remove(_kLlmApiBaseUrlKey);
    _controlRobotCode = _defaultControlRobotCode;
    _tcpHost = _defaultTcpHost;
    _tcpPort = _defaultTcpPort;
    _apiBaseUrl = _defaultApiBaseUrl;
    _llmApiBaseUrl = _defaultLlmApiBaseUrl;
    notifyListeners();
  }

  String _normalizeTcpHost(String host) {
    return _legacyTcpHosts[host.trim()] ?? host.trim();
  }

  String _normalizeApiBaseUrl(String? savedValue, String robotCode) {
    final selected = controlTargets.firstWhere(
      (target) => target.code == robotCode,
      orElse: () => controlTargets.first,
    );
    final clean = savedValue?.trim().replaceAll(RegExp(r'/+$'), '');
    if (clean == 'http://192.168.137.89:8000') {
      return 'http://192.168.137.95:8000';
    }
    if (clean == null || clean.isEmpty || _legacyApiBaseUrls.contains(clean)) {
      return selected.apiBaseUrl;
    }
    final isKnownRobotApi = controlTargets.any(
      (target) => target.apiBaseUrl == clean,
    );
    if (isKnownRobotApi && clean != selected.apiBaseUrl) {
      return selected.apiBaseUrl;
    }
    return clean;
  }

  RobotControlTarget? _targetForTcp(String host, int port) {
    for (final target in controlTargets) {
      if (target.host == host && target.tcpPort == port) return target;
    }
    return null;
  }

  RobotControlTarget? _targetForApi(String apiBaseUrl) {
    for (final target in controlTargets) {
      if (target.apiBaseUrl == apiBaseUrl) return target;
    }
    return null;
  }
}

class RobotControlTarget {
  final String code;
  final String label;
  final String host;
  final int tcpPort;
  final String apiBaseUrl;

  const RobotControlTarget({
    required this.code,
    required this.label,
    required this.host,
    required this.tcpPort,
    required this.apiBaseUrl,
  });
}
