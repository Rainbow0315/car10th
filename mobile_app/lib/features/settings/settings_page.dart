import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app/app_settings.dart';
import '../../app/session.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final _backend = TextEditingController();
  final _mqtt = TextEditingController();

  @override
  void dispose() {
    _backend.dispose();
    _mqtt.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<AppSettings>();
    final session = context.watch<AppSession>();
    final theme = Theme.of(context);

    if (_backend.text.isEmpty) _backend.text = settings.backendUrl;
    if (_mqtt.text.isEmpty) _mqtt.text = settings.mqttUrl;

    return Scaffold(
      appBar: AppBar(title: const Text('系统设置')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('账号信息', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 8),
                  _KvRow(k: '账号', v: session.username ?? '-'),
                  _KvRow(k: '角色', v: _roleLabel(session.role)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('连接配置', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _backend,
                    decoration: const InputDecoration(
                      labelText: '后端服务地址',
                      hintText: 'http://ip:8000',
                      border: OutlineInputBorder(),
                    ),
                    enabled: session.canSystemSettings(),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _mqtt,
                    decoration: const InputDecoration(
                      labelText: 'MQTT 地址',
                      hintText: 'mqtt://ip:1883',
                      border: OutlineInputBorder(),
                    ),
                    enabled: session.canSystemSettings(),
                  ),
                  const SizedBox(height: 10),
                  FilledButton.tonalIcon(
                    onPressed: session.canSystemSettings()
                        ? () async {
                            await settings.updateBackendUrl(_backend.text);
                            await settings.updateMqttUrl(_mqtt.text);
                            if (!context.mounted) return;
                            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('已保存配置')));
                          }
                        : null,
                    icon: const Icon(Icons.save_outlined),
                    label: const Text('保存'),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    session.canSystemSettings() ? '管理员可修改连接配置' : '当前角色无系统配置权限',
                    style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('缓存管理', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 10),
                  OutlinedButton.icon(
                    onPressed: () async {
                      await settings.clearLocalCache();
                      if (!context.mounted) return;
                      _backend.text = settings.backendUrl;
                      _mqtt.text = settings.mqttUrl;
                      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('已清理本地缓存')));
                    },
                    icon: const Icon(Icons.cleaning_services_outlined),
                    label: const Text('清理缓存'),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('安全', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 10),
                  FilledButton.icon(
                    onPressed: () async {
                      await context.read<AppSession>().logout();
                    },
                    icon: const Icon(Icons.logout),
                    label: const Text('退出登录'),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '修改密码功能待后端实现（FastAPI 权限管理模块）',
                    style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _roleLabel(UserRole? role) {
    switch (role) {
      case UserRole.admin:
        return '管理员';
      case UserRole.dutyOfficer:
        return '值班员';
      case UserRole.operator:
        return '运维人员';
      case null:
        return '-';
    }
  }
}

class _KvRow extends StatelessWidget {
  final String k;
  final String v;

  const _KvRow({required this.k, required this.v});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(k, style: theme.textTheme.bodyMedium),
          Text(v, style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}

