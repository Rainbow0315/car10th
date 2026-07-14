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
          host: '192.168.137.89',
          tcpPort: 6001,
          apiBaseUrl: 'http://192.168.137.89:8000',
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
    if (savedControlRobot != null &&
        controlTargets.any((target) => target.code == savedControlRobot)) {
      _controlRobotCode = savedControlRobot;
    }

    _tcpHost = prefs.getString(_kTcpHostKey) ?? _tcpHost;
    final savedTcpPort = prefs.getInt(_kTcpPortKey);
    _tcpPort = savedTcpPort == null || savedTcpPort == 6000
        ? _defaultTcpPort
        : savedTcpPort;
    if (savedTcpPort == 6000) {
      await prefs.setInt(_kTcpPortKey, _defaultTcpPort);
    }

    final savedApiBaseUrl = prefs.getString(_kApiBaseUrlKey);
    final savedLlmApiBaseUrl = prefs.getString(_kLlmApiBaseUrlKey);
    _apiBaseUrl =
        savedApiBaseUrl == null || _legacyApiBaseUrls.contains(savedApiBaseUrl)
            ? _defaultApiBaseUrl
            : savedApiBaseUrl;
    _llmApiBaseUrl = savedLlmApiBaseUrl ?? _llmApiBaseUrl;

    if (savedApiBaseUrl != null &&
        _legacyApiBaseUrls.contains(savedApiBaseUrl)) {
      await prefs.setString(_kApiBaseUrlKey, _defaultApiBaseUrl);
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

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kControlRobotCodeKey, target.code);
    await prefs.setString(_kTcpHostKey, target.host);
    await prefs.setInt(_kTcpPortKey, target.tcpPort);
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
