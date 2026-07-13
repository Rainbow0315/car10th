import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app/session.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../alarm/alarm_labels.dart';
import '../chat/chat_page.dart';
import '../control/control_page.dart';
import '../history/history_page.dart';
import '../inspection/camera_yolo_card.dart';
import '../task/task_config_page.dart';

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  late Future<DashboardStats> _statsFuture;

  @override
  void initState() {
    super.initState();
    _statsFuture = context.read<Repository>().getDashboardStats();
  }

  Future<void> _reload() async {
    final repo = context.read<Repository>();
    setState(() {
      _statsFuture = repo.getDashboardStats();
    });
    await _statsFuture;
  }

  void _push(Widget page) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
  }

  @override
  Widget build(BuildContext context) {
    final session = context.watch<AppSession>();

    return Scaffold(
      appBar: AppBar(title: const Text('总控首页')),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _buildQuickActions(session),
            const SizedBox(height: 12),
            const CameraYoloCard(title: '监测监控'),
            const SizedBox(height: 12),
            FutureBuilder<DashboardStats>(
              future: _statsFuture,
              builder: (context, snapshot) {
                if (!snapshot.hasData) {
                  return const _LoadingCard(title: '数据看板');
                }
                return _StatsCard(stats: snapshot.data!);
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildQuickActions(AppSession session) {
    final items = <_QuickAction>[
      _QuickAction(
        label: '单车遥控',
        icon: Icons.gamepad_outlined,
        enabled: session.canRemoteControl(),
        onTap: () => _push(const ControlPage()),
      ),
      _QuickAction(
        label: '任务配置',
        icon: Icons.route_outlined,
        enabled: session.canTaskConfig(),
        onTap: () => _push(const TaskConfigPage()),
      ),
      _QuickAction(
        label: '历史回放',
        icon: Icons.history,
        enabled: true,
        onTap: () => _push(const HistoryPage()),
      ),
      _QuickAction(
        label: 'LLM 对话',
        icon: Icons.chat_bubble_outline,
        enabled: true,
        onTap: () => _push(const ChatPage()),
      ),
    ];

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Wrap(
          spacing: 12,
          runSpacing: 12,
          children: items
              .map(
                (e) => SizedBox(
                  width: 160,
                  child: FilledButton.tonalIcon(
                    onPressed: e.enabled ? e.onTap : null,
                    icon: Icon(e.icon),
                    label: Text(e.label),
                  ),
                ),
              )
              .toList(),
        ),
      ),
    );
  }
}

class _QuickAction {
  final String label;
  final IconData icon;
  final bool enabled;
  final VoidCallback onTap;

  const _QuickAction({
    required this.label,
    required this.icon,
    required this.enabled,
    required this.onTap,
  });
}

class _LoadingCard extends StatelessWidget {
  final String title;

  const _LoadingCard({required this.title});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            const LinearProgressIndicator(),
          ],
        ),
      ),
    );
  }
}

class _StatsCard extends StatelessWidget {
  final DashboardStats stats;

  const _StatsCard({required this.stats});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final typeRows = AlarmType.values
        .map(
          (t) => Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(alarmTypeLabel(t), style: theme.textTheme.bodyMedium),
              Text(
                '${stats.alarmTypeCounts[t] ?? 0}',
                style: theme.textTheme.titleMedium,
              ),
            ],
          ),
        )
        .toList();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('数据看板', style: theme.textTheme.titleMedium),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: _Metric(
                    label: '在线小车',
                    value: '${stats.onlineRobots}',
                  ),
                ),
                Expanded(
                  child: _Metric(
                    label: '今日巡检',
                    value: '${stats.todayPatrolCount}',
                  ),
                ),
                Expanded(
                  child: _Metric(
                    label: '高危未处理',
                    value: '${stats.highRiskAlarmCount}',
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text('告警统计', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            ...typeRows,
          ],
        ),
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  final String label;
  final String value;

  const _Metric({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          value,
          maxLines: 1,
          softWrap: false,
          overflow: TextOverflow.ellipsis,
          style: theme.textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          label,
          maxLines: 1,
          softWrap: false,
          overflow: TextOverflow.ellipsis,
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}
