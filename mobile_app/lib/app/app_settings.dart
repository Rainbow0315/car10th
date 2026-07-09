import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AppSettings extends ChangeNotifier {
  static const _kTcpHostKey = 'settings.tcpHost';
  static const _kTcpPortKey = 'settings.tcpPort';

  String _tcpHost = '192.168.247.227';
  int _tcpPort = 6000;

  String get tcpHost => _tcpHost;
  int get tcpPort => _tcpPort;

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _tcpHost = prefs.getString(_kTcpHostKey) ?? _tcpHost;
    _tcpPort = prefs.getInt(_kTcpPortKey) ?? _tcpPort;
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

  Future<void> clearLocalCache() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kTcpHostKey);
    await prefs.remove(_kTcpPortKey);
    _tcpHost = '192.168.247.227';
    _tcpPort = 6000;
    notifyListeners();
  }
}
