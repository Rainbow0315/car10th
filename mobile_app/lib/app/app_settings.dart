import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AppSettings extends ChangeNotifier {
  static const _kBackendUrlKey = 'settings.backendUrl';
  static const _kMqttUrlKey = 'settings.mqttUrl';

  String _backendUrl = 'http://127.0.0.1:8000';
  String _mqttUrl = 'mqtt://127.0.0.1:1883';

  String get backendUrl => _backendUrl;
  String get mqttUrl => _mqttUrl;

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _backendUrl = prefs.getString(_kBackendUrlKey) ?? _backendUrl;
    _mqttUrl = prefs.getString(_kMqttUrlKey) ?? _mqttUrl;
    notifyListeners();
  }

  Future<void> updateBackendUrl(String value) async {
    final v = value.trim();
    if (v.isEmpty) return;
    _backendUrl = v;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kBackendUrlKey, v);
    notifyListeners();
  }

  Future<void> updateMqttUrl(String value) async {
    final v = value.trim();
    if (v.isEmpty) return;
    _mqttUrl = v;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kMqttUrlKey, v);
    notifyListeners();
  }

  Future<void> clearLocalCache() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kBackendUrlKey);
    await prefs.remove(_kMqttUrlKey);
    _backendUrl = 'http://127.0.0.1:8000';
    _mqttUrl = 'mqtt://127.0.0.1:1883';
    notifyListeners();
  }
}

