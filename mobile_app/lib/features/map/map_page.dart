import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../data/repository.dart';

class MapPage extends StatefulWidget {
  const MapPage({super.key});

  @override
  State<MapPage> createState() => _MapPageState();
}

class _MapPageState extends State<MapPage> {
  MapPoint _robot = const MapPoint(x: 6.0, y: 6.0, yaw: 0);
  MapPoint? _goal;

  Future<void> _sendGoal() async {
    final goal = _goal;
    if (goal == null) return;
    await context.read<Repository>().sendNavGoal(goal: goal);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content: Text(
              '已下发导航目标：(${goal.x.toStringAsFixed(2)}, ${goal.y.toStringAsFixed(2)})')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('地图巡检'),
        actions: [
          IconButton(
            onPressed: () => setState(() => _goal = null),
            icon: const Icon(Icons.clear),
            tooltip: '清除目标点',
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: Card(
                clipBehavior: Clip.antiAlias,
                child: LayoutBuilder(
                  builder: (context, c) {
                    final size = Size(c.maxWidth, c.maxHeight);
                    return GestureDetector(
                      onTapDown: (d) {
                        final p = d.localPosition;
                        final x = (p.dx / size.width) * 12;
                        final y = (p.dy / size.height) * 12;
                        setState(() => _goal = MapPoint(x: x, y: y, yaw: 0));
                      },
                      child: CustomPaint(
                        painter: _MapPainter(robot: _robot, goal: _goal),
                        child: const SizedBox.expand(),
                      ),
                    );
                  },
                ),
              ),
            ),
            const SizedBox(height: 12),
            Text(
              '点击地图下发单点导航目标（Mock）',
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => setState(() {
                      _robot = MapPoint(
                        x: _robot.x + 0.2,
                        y: _robot.y + 0.1,
                        yaw: _robot.yaw,
                      );
                    }),
                    icon: const Icon(Icons.my_location),
                    label: const Text('刷新坐标'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: _goal == null ? null : _sendGoal,
                    icon: const Icon(Icons.navigation_outlined),
                    label: const Text('下发目标'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('实时信息', style: theme.textTheme.titleSmall),
                    const SizedBox(height: 6),
                    Text(
                        '小车坐标：(${_robot.x.toStringAsFixed(2)}, ${_robot.y.toStringAsFixed(2)})'),
                    Text(_goal == null
                        ? '导航目标：未选择'
                        : '导航目标：(${_goal!.x.toStringAsFixed(2)}, ${_goal!.y.toStringAsFixed(2)})'),
                    Text(
                      '航点/路线/禁区/轨迹：后续对接后端下发与回放接口',
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MapPainter extends CustomPainter {
  final MapPoint robot;
  final MapPoint? goal;

  _MapPainter({
    required this.robot,
    required this.goal,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final bg = Paint()..color = const Color(0xFFF6F7FB);
    canvas.drawRect(Offset.zero & size, bg);

    final gridPaint = Paint()
      ..color = const Color(0xFFE2E5EF)
      ..strokeWidth = 1;
    for (var i = 0; i <= 12; i++) {
      final dx = (i / 12) * size.width;
      final dy = (i / 12) * size.height;
      canvas.drawLine(Offset(dx, 0), Offset(dx, size.height), gridPaint);
      canvas.drawLine(Offset(0, dy), Offset(size.width, dy), gridPaint);
    }

    final robotOffset =
        Offset((robot.x / 12) * size.width, (robot.y / 12) * size.height);
    final robotPaint = Paint()..color = const Color(0xFF1E5EFF);
    canvas.drawCircle(robotOffset, 8, robotPaint);

    if (goal != null) {
      final goalOffset =
          Offset((goal!.x / 12) * size.width, (goal!.y / 12) * size.height);
      final goalPaint = Paint()..color = const Color(0xFFFF4D4F);
      canvas.drawCircle(goalOffset, 7, goalPaint);
      final line = Paint()
        ..color = const Color(0x66FF4D4F)
        ..strokeWidth = 2;
      canvas.drawLine(robotOffset, goalOffset, line);
    }
  }

  @override
  bool shouldRepaint(covariant _MapPainter oldDelegate) {
    return oldDelegate.robot.x != robot.x ||
        oldDelegate.robot.y != robot.y ||
        oldDelegate.goal?.x != goal?.x ||
        oldDelegate.goal?.y != goal?.y;
  }
}
