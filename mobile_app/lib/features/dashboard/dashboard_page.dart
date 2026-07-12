import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app/session.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../chat/chat_page.dart';
import '../control/control_page.dart';
import '../history/history_page.dart';
import '../task/task_config_page.dart';

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  late Future<DashboardStats> _statsFuture;
  late Future<RobotStatus> _robotFuture;
  late Future<InspectionMonitorStatus> _monitorFuture;
  bool _monitorBusy = false;

  @override
  void initState() {
    super.initState();
    final repo = context.read<Repository>();
    _statsFuture = repo.getDashboardStats();
    _robotFuture = repo.getRobotStatus(robotId: 'robot_01');
    _monitorFuture = repo.getInspectionMonitorStatus();
  }

  String _alarmTypeLabel(AlarmType t) {
    switch (t) {
      case AlarmType.water:
        return '积水';
      case AlarmType.crack:
        return '裂缝';
      case AlarmType.debris:
        return '异物';
      case AlarmType.smoking:
        return '抽烟';
    }
  }

  String _modeLabel(RobotMode m) {
    switch (m) {
      case RobotMode.patrol:
        return '巡检';
      case RobotMode.follow:
        return '跟随';
      case RobotMode.standby:
        return '待机';
    }
  }

  void _push(Widget page) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
  }

  Future<void> _reload() async {
    final repo = context.read<Repository>();
    setState(() {
      _statsFuture = repo.getDashboardStats();
      _robotFuture = repo.getRobotStatus(robotId: 'robot_01');
      _monitorFuture = repo.getInspectionMonitorStatus();
    });
    await Future.wait([_statsFuture, _robotFuture, _monitorFuture]);
  }

  Future<void> _toggleMonitor(bool enable) async {
    setState(() => _monitorBusy = true);
    try {
      final repo = context.read<Repository>();
      final status = enable
          ? await repo.startInspectionMonitor()
          : await repo.stopInspectionMonitor();
      if (!mounted) return;
      setState(() {
        _monitorFuture = Future.value(status);
        _statsFuture = repo.getDashboardStats();
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Monitor command failed: $e')),
      );
    } finally {
      if (mounted) setState(() => _monitorBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = context.watch<AppSession>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('总控首页'),
      ),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _buildQuickActions(session),
            const SizedBox(height: 12),
            FutureBuilder(
              future: _monitorFuture,
              builder: (context, snapshot) {
                if (!snapshot.hasData) {
                  return const _LoadingCard(title: 'Inspection monitor');
                }
                return _MonitorCard(
                  status: snapshot.data!,
                  busy: _monitorBusy,
                  onChanged: _toggleMonitor,
                );
              },
            ),
            const SizedBox(height: 12),
            FutureBuilder(
              future: _statsFuture,
              builder: (context, snapshot) {
                if (!snapshot.hasData) {
                  return const _LoadingCard(title: '数据看板');
                }
                final stats = snapshot.data!;
                return _StatsCard(stats: stats, typeLabel: _alarmTypeLabel);
              },
            ),
            const SizedBox(height: 12),
            FutureBuilder(
              future: _robotFuture,
              builder: (context, snapshot) {
                if (!snapshot.hasData) {
                  return const _LoadingCard(title: '实时车辆状态');
                }
                final s = snapshot.data!;
                return _RobotCard(status: s, modeLabel: _modeLabel);
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

class _MonitorCard extends StatelessWidget {
  final InspectionMonitorStatus status;
  final bool busy;
  final ValueChanged<bool> onChanged;

  const _MonitorCard({
    required this.status,
    required this.busy,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final stateColor = status.running ? cs.primary : cs.onSurfaceVariant;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.visibility_outlined, color: stateColor),
                const SizedBox(width: 8),
                Expanded(
                  child: Text('Inspection monitor',
                      style: theme.textTheme.titleMedium),
                ),
                Switch(
                  value: status.running,
                  onChanged: busy ? null : onChanged,
                ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                    child: _Metric(label: 'Topic', value: status.topicName)),
                Expanded(
                    child: _Metric(
                        label: 'Frames', value: '${status.totalFrames}')),
                Expanded(
                    child: _Metric(
                        label: 'Alarms', value: '${status.totalAlarms}')),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              status.lastError?.isNotEmpty == true
                  ? 'Last error: ${status.lastError}'
                  : 'Interval ${status.intervalSec.toStringAsFixed(1)}s, risk frames ${status.totalAlarmFrames}',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: cs.onSurfaceVariant),
            ),
          ],
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
  final String Function(AlarmType) typeLabel;

  const _StatsCard({
    required this.stats,
    required this.typeLabel,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final typeRows = AlarmType.values
        .map(
          (t) => Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(typeLabel(t), style: theme.textTheme.bodyMedium),
              Text('${stats.alarmTypeCounts[t] ?? 0}',
                  style: theme.textTheme.titleMedium),
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
                    child:
                        _Metric(label: '在线小车', value: '${stats.onlineRobots}')),
                Expanded(
                    child: _Metric(
                        label: '今日巡检', value: '${stats.todayPatrolCount}')),
                Expanded(
                    child: _Metric(
                        label: '高危未处理', value: '${stats.highRiskAlarmCount}')),
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
        Text(value,
            style: theme.textTheme.headlineSmall
                ?.copyWith(fontWeight: FontWeight.w700)),
        const SizedBox(height: 2),
        Text(label,
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
      ],
    );
  }
}

class _RobotCard extends StatelessWidget {
  final RobotStatus status;
  final String Function(RobotMode) modeLabel;

  const _RobotCard({
    required this.status,
    required this.modeLabel,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('实时车辆状态', style: theme.textTheme.titleMedium),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: _Metric(
                    label: '剩余电量',
                    value: '${status.batteryPercent}%',
                  ),
                ),
                Expanded(
                  child: _Metric(
                    label: '工作模式',
                    value: modeLabel(status.mode),
                  ),
                ),
                Expanded(
                  child: _Metric(
                    label: '网络延迟',
                    value: '${status.latencyMs}ms',
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              '当前速度：${status.speedMps.toStringAsFixed(2)} m/s',
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}
