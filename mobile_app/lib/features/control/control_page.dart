import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../data/repository.dart';

class ControlPage extends StatefulWidget {
  const ControlPage({super.key});

  @override
  State<ControlPage> createState() => _ControlPageState();
}

class _ControlPageState extends State<ControlPage> {
  RobotMode _mode = RobotMode.standby;
  double _speed = 0.2;

  Future<void> _setMode(RobotMode mode) async {
    await context.read<Repository>().setRobotMode(robotId: 'robot_01', mode: mode);
    if (!mounted) return;
    setState(() => _mode = mode);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('已切换模式：${_modeLabel(mode)}')));
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

  void _showToast(String text) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text), duration: const Duration(milliseconds: 900)));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('单车遥控监控')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('实时传感器数据（Mock）', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 8),
                  const _KvRow(k: '雷达', v: '在线'),
                  const _KvRow(k: '网络延迟', v: '68ms'),
                  _KvRow(k: '当前速度', v: '${_speed.toStringAsFixed(2)} m/s'),
                  _KvRow(k: '工作模式', v: _modeLabel(_mode)),
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
                  Text('虚拟摇杆（占位）', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 12),
                  Center(
                    child: SizedBox(
                      width: 240,
                      height: 240,
                      child: Stack(
                        children: [
                          Align(
                            alignment: Alignment.topCenter,
                            child: IconButton.filledTonal(
                              onPressed: () => _showToast('前进（Mock）'),
                              icon: const Icon(Icons.keyboard_arrow_up),
                            ),
                          ),
                          Align(
                            alignment: Alignment.bottomCenter,
                            child: IconButton.filledTonal(
                              onPressed: () => _showToast('后退（Mock）'),
                              icon: const Icon(Icons.keyboard_arrow_down),
                            ),
                          ),
                          Align(
                            alignment: Alignment.centerLeft,
                            child: IconButton.filledTonal(
                              onPressed: () => _showToast('左转（Mock）'),
                              icon: const Icon(Icons.keyboard_arrow_left),
                            ),
                          ),
                          Align(
                            alignment: Alignment.centerRight,
                            child: IconButton.filledTonal(
                              onPressed: () => _showToast('右转（Mock）'),
                              icon: const Icon(Icons.keyboard_arrow_right),
                            ),
                          ),
                          Align(
                            alignment: Alignment.center,
                            child: CircleAvatar(
                              radius: 36,
                              child: Text(
                                '${(_speed * 100).round()}%',
                                style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    '速度档位（Mock）',
                    style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                  ),
                  Slider(
                    value: _speed,
                    min: 0.1,
                    max: 0.8,
                    divisions: 7,
                    label: '${_speed.toStringAsFixed(2)} m/s',
                    onChanged: (v) => setState(() => _speed = v),
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
                  Text('快捷功能', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      FilledButton.tonalIcon(
                        onPressed: () => _setMode(RobotMode.patrol),
                        icon: const Icon(Icons.play_circle_outline),
                        label: const Text('启停巡检'),
                      ),
                      FilledButton.tonalIcon(
                        onPressed: () => _setMode(RobotMode.follow),
                        icon: const Icon(Icons.group_outlined),
                        label: const Text('人员跟随'),
                      ),
                      FilledButton.tonalIcon(
                        onPressed: () => _showToast('返回起点（Mock）'),
                        icon: const Icon(Icons.home_outlined),
                        label: const Text('返回起点'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
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
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(k, style: theme.textTheme.bodyMedium),
          Text(v, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}

