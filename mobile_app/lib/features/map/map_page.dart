import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' show PointMode;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../data/repository.dart';

enum _MapMode {
  calibrate,
  navigate,
}

class MapPage extends StatefulWidget {
  const MapPage({super.key});

  @override
  State<MapPage> createState() => _MapPageState();
}

class _MapPageState extends State<MapPage> {
  SlamMap? _map;
  MapPoint? _initialPose;
  MapPoint? _goal;
  final TransformationController _mapTransformController =
      TransformationController();
  _MapMode _mode = _MapMode.calibrate;
  bool _calibrated = false;
  bool _loading = false;
  bool _submitting = false;
  bool _draggingPose = false;
  String? _error;
  Offset? _lastDoubleTapPosition;
  Timer? _refreshTimer;

  @override
  void initState() {
    super.initState();
    unawaited(_loadMap());
    _refreshTimer = Timer.periodic(
      const Duration(seconds: 2),
      (_) => unawaited(_loadMap(silent: true)),
    );
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _mapTransformController.dispose();
    super.dispose();
  }

  Future<void> _loadMap({bool silent = false}) async {
    if (_loading && silent) return;
    if (!silent && mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }

    try {
      final map = await context.read<Repository>().getSlamMap();
      if (!mounted) return;
      setState(() {
        _map = map;
        _initialPose ??= map.robotPose;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted && !silent) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _confirmInitialPose() async {
    final pose = _initialPose;
    if (pose == null) return;

    setState(() {
      _submitting = true;
      _error = null;
    });

    try {
      await context.read<Repository>().setInitialPose(pose: pose);
      if (!mounted) return;
      setState(() {
        _calibrated = true;
        _mode = _MapMode.navigate;
        _goal = null;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '已校准当前位置：(${pose.x.toStringAsFixed(2)}, ${pose.y.toStringAsFixed(2)}) yaw=${pose.yaw.toStringAsFixed(2)}',
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _sendGoal() async {
    final goal = _goal;
    if (!_calibrated || goal == null) return;

    setState(() {
      _submitting = true;
      _error = null;
    });

    try {
      await context.read<Repository>().sendNavGoal(goal: goal);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '已下发目标：(${goal.x.toStringAsFixed(2)}, ${goal.y.toStringAsFixed(2)}) yaw=${goal.yaw.toStringAsFixed(2)}',
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final map = _map;
    final hasGrid = map?.hasGrid == true;
    final calibrating = _mode == _MapMode.calibrate;

    return Scaffold(
      appBar: AppBar(
        title: const Text('建图导航'),
        actions: [
          IconButton(
            onPressed: _loading ? null : () => unawaited(_loadMap()),
            icon: _loading
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
            tooltip: '刷新地图',
          ),
          IconButton(
            onPressed: _resetCalibration,
            icon: const Icon(Icons.my_location),
            tooltip: '重新校准当前位置',
          ),
          IconButton(
            onPressed: () => setState(() => _goal = null),
            icon: const Icon(Icons.clear),
            tooltip: '清除目标',
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: const Color(0xFFF4F6F8),
                  border: Border.all(color: const Color(0xFFD7DDE5)),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(7),
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      final size = Size(
                        constraints.maxWidth,
                        constraints.maxHeight,
                      );
                      return InteractiveViewer(
                        transformationController: _mapTransformController,
                        minScale: 1,
                        maxScale: 5,
                        boundaryMargin: const EdgeInsets.all(96),
                        clipBehavior: Clip.none,
                        child: SizedBox(
                          width: size.width,
                          height: size.height,
                          child: GestureDetector(
                            behavior: HitTestBehavior.opaque,
                            onTapUp: hasGrid
                                ? (detail) => _setActivePosePosition(
                                      detail.localPosition,
                                      size,
                                      map!,
                                    )
                                : null,
                            onDoubleTapDown: hasGrid
                                ? (detail) {
                                    _lastDoubleTapPosition =
                                        detail.localPosition;
                                  }
                                : null,
                            onDoubleTap: hasGrid ? _toggleMapZoom : null,
                            onLongPressStart: hasGrid
                                ? (detail) {
                                    _draggingPose = true;
                                    _setActivePosePosition(
                                      detail.localPosition,
                                      size,
                                      map!,
                                    );
                                  }
                                : null,
                            onLongPressMoveUpdate: hasGrid
                                ? (detail) => _setActivePoseYaw(
                                      detail.localPosition,
                                      size,
                                      map!,
                                    )
                                : null,
                            onLongPressEnd: (_) => _draggingPose = false,
                            onLongPressCancel: () => _draggingPose = false,
                            child: CustomPaint(
                              painter: _SlamMapPainter(
                                map: map,
                                initialPose: _initialPose,
                                goal: _goal,
                                calibrated: _calibrated,
                              ),
                              child: _MapOverlay(
                                loading: _loading && map == null,
                                error: _error,
                                hasGrid: hasGrid,
                              ),
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                OutlinedButton.icon(
                  onPressed: _loading ? null : () => unawaited(_loadMap()),
                  icon: const Icon(Icons.radar),
                  label: const Text('刷新地图'),
                ),
                OutlinedButton.icon(
                  onPressed: _submitting ? null : _resetCalibration,
                  icon: const Icon(Icons.my_location),
                  label: Text(_calibrated ? '重新校准' : '校准当前位置'),
                ),
                FilledButton.icon(
                  onPressed: calibrating ||
                          _initialPose == null ||
                          _goal == null ||
                          _submitting
                      ? null
                      : _sendGoal,
                  icon: const Icon(Icons.navigation_outlined),
                  label: Text(_calibrated ? '下发目标' : '先完成校准'),
                ),
              ],
            ),
            const SizedBox(height: 10),
            DecoratedBox(
              decoration: BoxDecoration(
                color: calibrating
                    ? const Color(0xFFFFFAEC)
                    : const Color(0xFFF8FAFC),
                border: Border.all(
                  color: calibrating
                      ? const Color(0xFFE2BE63)
                      : const Color(0xFFE1E6EE),
                ),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: DefaultTextStyle(
                  style: theme.textTheme.bodyMedium!,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        calibrating ? '步骤 1：校准当前位置' : '步骤 2：选择导航目标',
                        style: theme.textTheme.titleSmall,
                      ),
                      const SizedBox(height: 6),
                      Text(_mapSummary(map)),
                      Text(_initialPoseSummary()),
                      Text(_goalSummary()),
                      Text(
                        _draggingPose
                            ? '操作：松手后保留当前箭头朝向'
                            : calibrating
                                ? '操作：点按设置小车当前位置，长按拖动设置当前朝向，然后确认校准。'
                                : '操作：点按设置目标位置，长按拖动设置最终朝向，双指缩放，双击放大/复位。',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                      if (calibrating) ...[
                        const SizedBox(height: 10),
                        FilledButton.icon(
                          onPressed: _initialPose == null || _submitting
                              ? null
                              : _confirmInitialPose,
                          icon: _submitting
                              ? const SizedBox.square(
                                  dimension: 16,
                                  child:
                                      CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Icon(Icons.check_circle_outline),
                          label: const Text('确认当前位置'),
                        ),
                      ],
                      if (_error != null) ...[
                        const SizedBox(height: 6),
                        Text(
                          _error!,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(color: theme.colorScheme.error),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _resetCalibration() {
    setState(() {
      _mode = _MapMode.calibrate;
      _calibrated = false;
      _goal = null;
      _initialPose = _map?.robotPose ?? _initialPose;
    });
  }

  void _setActivePosePosition(Offset canvasPoint, Size size, SlamMap map) {
    final point = _canvasToMap(canvasPoint, size, map);
    if (_mode == _MapMode.calibrate) {
      final existingYaw = _initialPose?.yaw ?? map.robotPose?.yaw ?? 0.0;
      setState(() {
        _initialPose = MapPoint(x: point.x, y: point.y, yaw: existingYaw);
      });
      return;
    }

    if (!_calibrated) return;
    final existingYaw = _goal?.yaw ?? map.robotPose?.yaw ?? 0.0;
    setState(() {
      _goal = MapPoint(x: point.x, y: point.y, yaw: existingYaw);
    });
  }

  void _setActivePoseYaw(Offset canvasPoint, Size size, SlamMap map) {
    final activePose = _mode == _MapMode.calibrate ? _initialPose : _goal;
    if (activePose == null) return;

    final dragPoint = _canvasToMap(canvasPoint, size, map);
    final dx = dragPoint.x - activePose.x;
    final dy = dragPoint.y - activePose.y;
    if ((dx * dx + dy * dy) < 0.0004) return;

    final updated = MapPoint(
      x: activePose.x,
      y: activePose.y,
      yaw: math.atan2(dy, dx),
    );
    setState(() {
      if (_mode == _MapMode.calibrate) {
        _initialPose = updated;
      } else if (_calibrated) {
        _goal = updated;
      }
    });
  }

  void _toggleMapZoom() {
    final currentScale = _mapTransformController.value.getMaxScaleOnAxis();
    if (currentScale > 1.05) {
      _mapTransformController.value = Matrix4.identity();
      return;
    }

    final focalPoint = _lastDoubleTapPosition ?? Offset.zero;
    const targetScale = 2.5;
    _mapTransformController.value = Matrix4.identity()
      ..translateByDouble(
        -focalPoint.dx * (targetScale - 1),
        -focalPoint.dy * (targetScale - 1),
        0,
        1,
      )
      ..scaleByDouble(targetScale, targetScale, 1, 1);
  }

  MapPoint _canvasToMap(Offset point, Size size, SlamMap map) {
    final scale = _mapScale(size, map);
    final drawWidth = map.width * scale;
    final drawHeight = map.height * scale;
    final left = (size.width - drawWidth) / 2;
    final top = (size.height - drawHeight) / 2;
    final gx = ((point.dx - left) / scale).clamp(0.0, map.width - 1.0);
    final gyFromTop = ((point.dy - top) / scale).clamp(0.0, map.height - 1.0);
    final gy = map.height - gyFromTop;
    return MapPoint(
      x: map.origin.x + gx * map.resolution,
      y: map.origin.y + gy * map.resolution,
      yaw: 0,
    );
  }

  String _mapSummary(SlamMap? map) {
    if (map == null) return '地图：等待数据';
    if (!map.hasGrid) return '地图：暂无 /map 数据';
    final widthM = map.width * map.resolution;
    final heightM = map.height * map.resolution;
    return '地图：${map.width} x ${map.height}，${widthM.toStringAsFixed(1)}m x ${heightM.toStringAsFixed(1)}m，雷达点 ${map.laserPoints.length}';
  }

  String _initialPoseSummary() {
    final pose = _initialPose;
    if (pose == null) return '校准：未选择当前位置';
    final status = _calibrated ? '已确认' : '待确认';
    return '校准：$status (${pose.x.toStringAsFixed(2)}, ${pose.y.toStringAsFixed(2)}) yaw=${pose.yaw.toStringAsFixed(2)}';
  }

  String _goalSummary() {
    if (!_calibrated) return '目标：完成校准后才可选择';
    final goal = _goal;
    if (goal == null) return '目标：点按地图选择';
    return '目标：(${goal.x.toStringAsFixed(2)}, ${goal.y.toStringAsFixed(2)}) yaw=${goal.yaw.toStringAsFixed(2)}';
  }
}

class _MapOverlay extends StatelessWidget {
  final bool loading;
  final String? error;
  final bool hasGrid;

  const _MapOverlay({
    required this.loading,
    required this.error,
    required this.hasGrid,
  });

  @override
  Widget build(BuildContext context) {
    if (hasGrid) return const SizedBox.expand();
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (loading)
              const CircularProgressIndicator()
            else
              Icon(
                Icons.map_outlined,
                size: 42,
                color: theme.colorScheme.outline,
              ),
            const SizedBox(height: 12),
            Text(
              loading ? '正在读取地图' : '暂无地图数据',
              style: theme.textTheme.titleMedium,
            ),
            const SizedBox(height: 6),
            Text(
              error ?? '请确认车端已启动 map_server 或建图节点，且 /map 正在发布。',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SlamMapPainter extends CustomPainter {
  final SlamMap? map;
  final MapPoint? initialPose;
  final MapPoint? goal;
  final bool calibrated;

  _SlamMapPainter({
    required this.map,
    required this.initialPose,
    required this.goal,
    required this.calibrated,
  });

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(
      Offset.zero & size,
      Paint()..color = const Color(0xFFF4F6F8),
    );

    final current = map;
    if (current == null || !current.hasGrid) return;

    final scale = _mapScale(size, current);
    final drawWidth = current.width * scale;
    final drawHeight = current.height * scale;
    final left = (size.width - drawWidth) / 2;
    final top = (size.height - drawHeight) / 2;

    final unknownPaint = Paint()..color = const Color(0xFFD5DBE3);
    final freePaint = Paint()..color = const Color(0xFFFDFDFB);
    final occupiedPaint = Paint()..color = const Color(0xFF222831);
    final cellStep = math.max(
      1,
      math.max(current.width / 240, current.height / 240).ceil(),
    );
    final cellSize = math.max(scale * cellStep, 1.0);

    canvas.drawRect(
      Rect.fromLTWH(left, top, drawWidth, drawHeight),
      Paint()..color = const Color(0xFFE8EDF3),
    );

    for (var y = 0; y < current.height; y += cellStep) {
      for (var x = 0; x < current.width; x += cellStep) {
        final value = current.data[y * current.width + x];
        final paint = value < 0
            ? unknownPaint
            : value >= 65
                ? occupiedPaint
                : freePaint;
        final px = left + x * scale;
        final py = top + (current.height - y - cellStep) * scale;
        canvas.drawRect(Rect.fromLTWH(px, py, cellSize, cellSize), paint);
      }
    }

    _drawLaserPoints(canvas, size, current);
    _drawRobot(canvas, size, current);
    _drawPoseMarker(
      canvas,
      size,
      current,
      initialPose,
      calibrated ? const Color(0xFF2E9D58) : const Color(0xFFD49A1E),
      24,
    );
    _drawPoseMarker(canvas, size, current, goal, const Color(0xFFE23B3B), 28);

    canvas.drawRect(
      Rect.fromLTWH(left, top, drawWidth, drawHeight),
      Paint()
        ..color = const Color(0xFF9AA7B4)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1,
    );
  }

  void _drawLaserPoints(Canvas canvas, Size size, SlamMap map) {
    if (map.laserPoints.isEmpty) return;
    final paint = Paint()
      ..color = const Color(0xFFE23B3B)
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 2.4;
    final points = <Offset>[];
    for (final point in map.laserPoints) {
      if (!_pointInsideMap(point, map)) continue;
      points.add(_mapToCanvas(point, size, map));
    }
    canvas.drawPoints(PointMode.points, points, paint);
  }

  void _drawRobot(Canvas canvas, Size size, SlamMap map) {
    final robot = map.robotPose;
    if (robot == null) return;
    final p = _mapToCanvas(robot, size, map);
    final paint = Paint()
      ..color = const Color(0xFF1E5EFF)
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    canvas.drawCircle(p, 7, Paint()..color = const Color(0xFF1E5EFF));
    _drawArrow(canvas, p, robot.yaw, 18, paint);
  }

  void _drawPoseMarker(
    Canvas canvas,
    Size size,
    SlamMap map,
    MapPoint? pose,
    Color color,
    double arrowLength,
  ) {
    if (pose == null) return;
    final p = _mapToCanvas(pose, size, map);
    canvas.drawCircle(p, 8, Paint()..color = color);
    canvas.drawCircle(
      p,
      13,
      Paint()
        ..color = color.withValues(alpha: 0.35)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2,
    );
    _drawArrow(
      canvas,
      p,
      pose.yaw,
      arrowLength,
      Paint()
        ..color = color
        ..strokeWidth = 3
        ..strokeCap = StrokeCap.round,
    );
  }

  void _drawArrow(
    Canvas canvas,
    Offset origin,
    double yaw,
    double length,
    Paint paint,
  ) {
    final end =
        origin + Offset(math.cos(yaw) * length, -math.sin(yaw) * length);
    canvas.drawLine(origin, end, paint);
    final left = end +
        Offset(
          math.cos(yaw + math.pi * 0.78) * 9,
          -math.sin(yaw + math.pi * 0.78) * 9,
        );
    final right = end +
        Offset(
          math.cos(yaw - math.pi * 0.78) * 9,
          -math.sin(yaw - math.pi * 0.78) * 9,
        );
    canvas.drawLine(end, left, paint);
    canvas.drawLine(end, right, paint);
  }

  bool _pointInsideMap(MapPoint point, SlamMap map) {
    final gx = (point.x - map.origin.x) / map.resolution;
    final gy = (point.y - map.origin.y) / map.resolution;
    return gx >= 0 && gy >= 0 && gx < map.width && gy < map.height;
  }

  @override
  bool shouldRepaint(covariant _SlamMapPainter oldDelegate) {
    return oldDelegate.map != map ||
        oldDelegate.initialPose != initialPose ||
        oldDelegate.goal != goal ||
        oldDelegate.calibrated != calibrated;
  }
}

double _mapScale(Size size, SlamMap map) {
  final sx = size.width / map.width;
  final sy = size.height / map.height;
  return math.min(sx, sy);
}

Offset _mapToCanvas(MapPoint point, Size size, SlamMap map) {
  final scale = _mapScale(size, map);
  final drawWidth = map.width * scale;
  final drawHeight = map.height * scale;
  final left = (size.width - drawWidth) / 2;
  final top = (size.height - drawHeight) / 2;
  final gx = (point.x - map.origin.x) / map.resolution;
  final gy = (point.y - map.origin.y) / map.resolution;
  return Offset(
    left + gx * scale,
    top + (map.height - gy) * scale,
  );
}
