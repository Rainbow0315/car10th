import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum UserRole {
  admin,
  dutyOfficer,
  operator,
}

class AppSession extends ChangeNotifier {
  static const _kTokenKey = 'session.token';
  static const _kRoleKey = 'session.role';
  static const _kUsernameKey = 'session.username';

  String? _token;
  String? _username;
  UserRole? _role;

  bool get isLoggedIn => _token != null && _role != null;
  String? get username => _username;
  UserRole? get role => _role;

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString(_kTokenKey);
    final roleStr = prefs.getString(_kRoleKey);
    final username = prefs.getString(_kUsernameKey);
    final role = _parseRole(roleStr);

    _token = token;
    _role = role;
    _username = username;
    notifyListeners();
  }

  Future<void> login({
    required String username,
    required String password,
  }) async {
    final role = _inferRole(username);
    final token = 'mock_token_${DateTime.now().millisecondsSinceEpoch}';

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kTokenKey, token);
    await prefs.setString(_kRoleKey, role.name);
    await prefs.setString(_kUsernameKey, username);

    _token = token;
    _role = role;
    _username = username;
    notifyListeners();
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kTokenKey);
    await prefs.remove(_kRoleKey);
    await prefs.remove(_kUsernameKey);

    _token = null;
    _role = null;
    _username = null;
    notifyListeners();
  }

  bool canManageUsers() => _role == UserRole.admin;
  bool canSystemSettings() => _role == UserRole.admin;
  bool canTaskConfig() =>
      _role == UserRole.admin ||
      _role == UserRole.dutyOfficer ||
      _role == UserRole.operator;
  bool canRemoteControl() =>
      _role == UserRole.admin || _role == UserRole.operator;
  bool canHandleAlarm() =>
      _role == UserRole.admin ||
      _role == UserRole.operator ||
      _role == UserRole.dutyOfficer;

  UserRole _inferRole(String username) {
    final s = username.toLowerCase();
    if (s.startsWith('admin')) return UserRole.admin;
    if (s.startsWith('duty')) return UserRole.dutyOfficer;
    return UserRole.operator;
  }

  UserRole? _parseRole(String? roleStr) {
    if (roleStr == null) return null;
    for (final r in UserRole.values) {
      if (r.name == roleStr) return r;
    }
    return null;
  }
}
