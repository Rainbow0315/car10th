import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'app_settings.dart';

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

  final AppSettings settings;

  AppSession({required this.settings});

  bool get isLoggedIn => _token != null && _role != null;
  String? get token => _token;
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
    final uri = _uri('/api/auth/login');
    final response = await http
        .post(
          uri,
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'username': username.trim(),
            'password': password,
          }),
        )
        .timeout(const Duration(seconds: 10));

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError(_errorMessage(response, uri));
    }

    final payload =
        jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    final token = payload['access_token'] as String?;
    final user = payload['user'] as Map<String, dynamic>?;
    final roleJson = user?['role'] as Map<String, dynamic>?;
    final roleCode = roleJson?['role_code'] as String?;
    if (token == null || token.isEmpty || roleCode == null) {
      throw StateError('登录响应缺少 token 或角色信息');
    }

    final role = _parseRoleCode(roleCode);

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kTokenKey, token);
    await prefs.setString(_kRoleKey, role.name);
    await prefs.setString(_kUsernameKey, username.trim());

    _token = token;
    _role = role;
    _username = username.trim();
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

  UserRole? _parseRole(String? roleStr) {
    if (roleStr == null) return null;
    for (final r in UserRole.values) {
      if (r.name == roleStr) return r;
    }
    return null;
  }

  UserRole _parseRoleCode(String roleCode) {
    switch (roleCode) {
      case 'admin':
        return UserRole.admin;
      case 'dutyOfficer':
      case 'duty_officer':
      case 'duty':
        return UserRole.dutyOfficer;
      case 'operator':
      case 'maintainer':
        return UserRole.operator;
      default:
        throw StateError('未知用户角色：$roleCode');
    }
  }

  Uri _uri(String path) {
    final base = settings.apiBaseUrl.replaceAll(RegExp(r'/+$'), '');
    final cleanPath = path.startsWith('/') ? path : '/$path';
    return Uri.parse('$base$cleanPath');
  }

  String _errorMessage(http.Response response, Uri uri) {
    var detail = response.body;
    try {
      final json = jsonDecode(utf8.decode(response.bodyBytes));
      if (json is Map<String, dynamic> && json['detail'] != null) {
        detail = json['detail'].toString();
      }
    } catch (_) {
      // Keep raw body when backend does not return JSON.
    }
    return 'HTTP ${response.statusCode} from $uri: $detail';
  }
}
