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
  final _tcpHost = TextEditingController();
  final _tcpPort = TextEditingController();
  final _apiBaseUrl = TextEditingController();
  final _llmApiBaseUrl = TextEditingController();

  @override
  void dispose() {
    _tcpHost.dispose();
    _tcpPort.dispose();
    _apiBaseUrl.dispose();
    _llmApiBaseUrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<AppSettings>();
    final session = context.watch<AppSession>();
    final theme = Theme.of(context);

    if (_tcpHost.text.isEmpty) _tcpHost.text = settings.tcpHost;
    if (_tcpPort.text.isEmpty) _tcpPort.text = settings.tcpPort.toString();
    if (_apiBaseUrl.text.isEmpty) _apiBaseUrl.text = settings.apiBaseUrl;
    if (_llmApiBaseUrl.text.isEmpty) {
      _llmApiBaseUrl.text = settings.llmApiBaseUrl;
    }

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
                  Text('后端接口', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _apiBaseUrl,
                    keyboardType: TextInputType.url,
                    decoration: const InputDecoration(
                      labelText: '接口地址',
                      hintText: 'http://192.168.137.239:8000',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 10),
                  FilledButton.tonalIcon(
                    onPressed: () async {
                      await settings.updateApiBaseUrl(_apiBaseUrl.text);
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text('已保存接口地址：${settings.apiBaseUrl}'),
                        ),
                      );
                    },
                    icon: const Icon(Icons.cloud_sync_outlined),
                    label: const Text('保存接口地址'),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _llmApiBaseUrl,
                    keyboardType: TextInputType.url,
                    decoration: const InputDecoration(
                      labelText: 'LLM 网关地址',
                      hintText: 'http://192.168.137.51:8000',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 10),
                  FilledButton.tonalIcon(
                    onPressed: () async {
                      await settings.updateLlmApiBaseUrl(_llmApiBaseUrl.text);
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content:
                              Text('已保存 LLM 网关地址：${settings.llmApiBaseUrl}'),
                        ),
                      );
                    },
                    icon: const Icon(Icons.smart_toy_outlined),
                    label: const Text('保存 LLM 网关地址'),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '助手页面只会使用 LLM 网关地址；地图、巡检、车队等接口仍使用上面的后端接口地址。',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
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
                  Text('小车 TCP 控制', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _tcpHost,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: '小车 IP',
                      hintText: '192.168.137.239',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _tcpPort,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'TCP 端口',
                      hintText: '6001',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 10),
                  FilledButton.tonalIcon(
                    onPressed: () async {
                      await settings.updateTcpConnection(
                        host: _tcpHost.text,
                        port: _tcpPort.text,
                      );
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(
                            '已保存 TCP：${settings.tcpHost}:${settings.tcpPort}',
                          ),
                        ),
                      );
                    },
                    icon: const Icon(Icons.save_outlined),
                    label: const Text('保存 TCP 配置'),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '控制页会直接向这个地址发送 Yahboom TCP 私有协议。',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
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
                      _tcpHost.text = settings.tcpHost;
                      _tcpPort.text = settings.tcpPort.toString();
                      _apiBaseUrl.text = settings.apiBaseUrl;
                      _llmApiBaseUrl.text = settings.llmApiBaseUrl;
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('已恢复默认配置')),
                      );
                    },
                    icon: const Icon(Icons.cleaning_services_outlined),
                    label: const Text('恢复默认配置'),
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
          const SizedBox(width: 12),
          Flexible(
            child: Text(
              v,
              maxLines: 1,
              softWrap: false,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.end,
              style: theme.textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
