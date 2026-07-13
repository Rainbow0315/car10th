import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AppSettings extends ChangeNotifier {
  static const _kTcpHostKey = 'settings.tcpHost';
  static const _kTcpPortKey = 'settings.tcpPort';
  static const _kApiBaseUrlKey = 'settings.apiBaseUrl';
  static const _defaultTcpHost = '192.168.137.239';
  static const _defaultTcpPort = 6001;
  static const _defaultApiBaseUrl = 'http://192.168.137.51:8000';

  String _tcpHost = _defaultTcpHost;
  int _tcpPort = _defaultTcpPort;
  String _apiBaseUrl = _defaultApiBaseUrl;

  String get tcpHost => _tcpHost;
  int get tcpPort => _tcpPort;
  String get apiBaseUrl => _apiBaseUrl;

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _tcpHost = prefs.getString(_kTcpHostKey) ?? _tcpHost;
    final savedTcpPort = prefs.getInt(_kTcpPortKey);
    _tcpPort = savedTcpPort == null || savedTcpPort == 6000
        ? _defaultTcpPort
        : savedTcpPort;
    if (savedTcpPort == 6000) {
      await prefs.setInt(_kTcpPortKey, _defaultTcpPort);
    }
    _apiBaseUrl = prefs.getString(_kApiBaseUrlKey) ?? _apiBaseUrl;
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
    final prefs = await SharedPreferences.getInstance();
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

  Future<void> clearLocalCache() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kTcpHostKey);
    await prefs.remove(_kTcpPortKey);
    await prefs.remove(_kApiBaseUrlKey);
    _tcpHost = _defaultTcpHost;
    _tcpPort = _defaultTcpPort;
    _apiBaseUrl = _defaultApiBaseUrl;
    notifyListeners();
  }
}
