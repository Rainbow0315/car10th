import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' show PointMode;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app/app_settings.dart';
import '../../data/models.dart';
import '../../data/repository.dart';

enum _MapMode {
  calibrate,
  navigate,
  patrol,
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
  final List<MapPoint> _patrolWaypoints = [];
  final TransformationController _mapTransformController =
      TransformationController();
  _MapMode _mode = _MapMode.calibrate;
  bool _calibrated = false;
  bool _loading = false;
  bool _submitting = false;
  bool _savingPatrol = false;
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

  Future<void> _savePatrolTask({bool scheduled = false}) async {
    if (_patrolWaypoints.length < 2) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('至少选择 2 个巡航航点')),
      );
      return;
    }

    final now = DateTime.now();
    final defaultName =
        '地图巡航 ${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}';
    final draft = await showDialog<_PatrolSaveDraft>(
      context: context,
      builder: (context) => _PatrolSaveDialog(
        defaultName: defaultName,
        scheduled: scheduled,
      ),
    );
    if (draft == null || !mounted) return;

    setState(() {
      _savingPatrol = true;
      _error = null;
    });

    try {
      final robotCode = context.read<AppSettings>().selectedControlTarget.code;
      final waypoints = _patrolWaypoints
          .asMap()
          .entries
          .map(
            (entry) => PatrolWaypointConfig(
              seq: entry.key + 1,
              name: '航点 ${entry.key + 1}',
              point: entry.value,
            ),
          )
          .toList(growable: false);
      final task = await context.read<Repository>().createPatrolTask(
            name: draft.name,
            robotCode: robotCode,
            waypoints: waypoints,
            loopCount: draft.loopCount,
            scheduleCron: draft.scheduleCron,
          );
      if (!mounted) return;
      if (draft.startAfterSave) {
        await context.read<Repository>().startPatrolTask(task.taskCode);
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('已保存并开始巡航：${task.name}')),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('已保存巡航任务：${draft.name}')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('巡航任务处理失败：$e')),
      );
    } finally {
      if (mounted) setState(() => _savingPatrol = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final map = _map;
    final hasGrid = map?.hasGrid == true;
    final calibrating = _mode == _MapMode.calibrate;
    final navigating = _mode == _MapMode.navigate;
    final patrolEditing = _mode == _MapMode.patrol;

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
            onPressed: () => setState(() {
              _goal = null;
              if (_mode == _MapMode.patrol) _patrolWaypoints.clear();
            }),
            icon: const Icon(Icons.clear),
            tooltip: patrolEditing ? '清空巡航路线' : '清除目标',
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
                                goal: patrolEditing ? null : _goal,
                                patrolWaypoints: List<MapPoint>.unmodifiable(
                                    _patrolWaypoints),
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
            SegmentedButton<_MapMode>(
              segments: const [
                ButtonSegment(
                  value: _MapMode.calibrate,
                  icon: Icon(Icons.my_location),
                  label: Text('校准'),
                ),
                ButtonSegment(
                  value: _MapMode.navigate,
                  icon: Icon(Icons.navigation_outlined),
                  label: Text('导航'),
                ),
                ButtonSegment(
                  value: _MapMode.patrol,
                  icon: Icon(Icons.alt_route_outlined),
                  label: Text('巡航'),
                ),
              ],
              selected: {_mode},
              onSelectionChanged: _submitting || _savingPatrol
                  ? null
                  : (selection) => setState(() => _mode = selection.first),
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
                  onPressed: !navigating ||
                          _initialPose == null ||
                          _goal == null ||
                          _submitting
                      ? null
                      : _sendGoal,
                  icon: const Icon(Icons.navigation_outlined),
                  label: Text(_calibrated ? '下发目标' : '先完成校准'),
                ),
                OutlinedButton.icon(
                  onPressed: patrolEditing && _patrolWaypoints.isNotEmpty
                      ? () => setState(() => _patrolWaypoints.removeLast())
                      : null,
                  icon: const Icon(Icons.undo),
                  label: const Text('撤销航点'),
                ),
                FilledButton.icon(
                  onPressed: patrolEditing && !_savingPatrol
                      ? () => unawaited(_savePatrolTask())
                      : null,
                  icon: _savingPatrol
                      ? const SizedBox.square(
                          dimension: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.save_outlined),
                  label: const Text('保存巡航路线'),
                ),
                FilledButton.tonalIcon(
                  onPressed: patrolEditing && !_savingPatrol
                      ? () => unawaited(_savePatrolTask(scheduled: true))
                      : null,
                  icon: const Icon(Icons.schedule),
                  label: const Text('保存定时巡航'),
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
                        calibrating
                            ? '步骤 1：校准当前位置'
                            : patrolEditing
                                ? '巡航路线：地图选点'
                                : '步骤 2：选择导航目标',
                        style: theme.textTheme.titleSmall,
                      ),
                      const SizedBox(height: 6),
                      Text(_mapSummary(map)),
                      Text(_initialPoseSummary()),
                      Text(patrolEditing ? _patrolSummary() : _goalSummary()),
                      Text(
                        _draggingPose
                            ? '操作：松手后保留当前箭头朝向'
                            : calibrating
                                ? '操作：点按设置小车当前位置，长按拖动设置当前朝向，然后确认校准。'
                                : patrolEditing
                                    ? '操作：点按地图追加巡航航点，长按拖动设置最后一个航点朝向，双指缩放，双击放大/复位。'
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

    if (_mode == _MapMode.patrol) {
      final existingYaw = _patrolWaypoints.isNotEmpty
          ? _patrolWaypoints.last.yaw
          : map.robotPose?.yaw ?? 0.0;
      setState(() {
        _patrolWaypoints.add(
          MapPoint(x: point.x, y: point.y, yaw: existingYaw),
        );
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
    final activePose = _mode == _MapMode.calibrate
        ? _initialPose
        : _mode == _MapMode.patrol
            ? (_patrolWaypoints.isEmpty ? null : _patrolWaypoints.last)
            : _goal;
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
      } else if (_mode == _MapMode.patrol && _patrolWaypoints.isNotEmpty) {
        _patrolWaypoints[_patrolWaypoints.length - 1] = updated;
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

  String _patrolSummary() {
    if (_patrolWaypoints.isEmpty) return '巡航：点按地图添加航点';
    final last = _patrolWaypoints.last;
    return '巡航：${_patrolWaypoints.length} 个航点，最后 (${last.x.toStringAsFixed(2)}, ${last.y.toStringAsFixed(2)}) yaw=${last.yaw.toStringAsFixed(2)}';
  }
}

class _PatrolSaveDraft {
  final String name;
  final int loopCount;
  final String? scheduleCron;
  final bool startAfterSave;

  const _PatrolSaveDraft({
    required this.name,
    required this.loopCount,
    required this.scheduleCron,
    required this.startAfterSave,
  });
}

class _PatrolSaveDialog extends StatefulWidget {
  final String defaultName;
  final bool scheduled;

  const _PatrolSaveDialog({
    required this.defaultName,
    required this.scheduled,
  });

  @override
  State<_PatrolSaveDialog> createState() => _PatrolSaveDialogState();
}

class _PatrolSaveDialogState extends State<_PatrolSaveDialog> {
  late final TextEditingController _name;
  late final TextEditingController _intervalMinutes;
  late bool _startAfterSave;
  String? _error;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.defaultName);
    _intervalMinutes = TextEditingController(text: '30');
    _startAfterSave = true;
  }

  @override
  void dispose() {
    _name.dispose();
    _intervalMinutes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.scheduled ? '保存定时巡航' : '保存巡航路线'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _name,
            decoration: const InputDecoration(labelText: '名称'),
          ),
          if (widget.scheduled)
            TextField(
              controller: _intervalMinutes,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: '每隔多少分钟巡航一次',
                suffixText: '分钟',
              ),
            ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            value: _startAfterSave,
            onChanged: (value) => setState(() => _startAfterSave = value),
            title: const Text('保存后立即巡航一次'),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('取消'),
        ),
        FilledButton(
          onPressed: () {
            final name = _name.text.trim();
            if (name.isEmpty) {
              setState(() => _error = '先填一个名称');
              return;
            }
            String? scheduleCron;
            if (widget.scheduled) {
              final minutes = int.tryParse(_intervalMinutes.text.trim());
              if (minutes == null || minutes < 1 || minutes > 59) {
                setState(() => _error = '间隔分钟填 1 到 59 之间的数字');
                return;
              }
              scheduleCron = '*/$minutes * * * *';
            }
            Navigator.of(context).pop(
              _PatrolSaveDraft(
                name: name,
                loopCount: 1,
                scheduleCron: scheduleCron,
                startAfterSave: _startAfterSave,
              ),
            );
          },
          child: const Text('保存'),
        ),
      ],
    );
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
  final List<MapPoint> patrolWaypoints;
  final bool calibrated;

  _SlamMapPainter({
    required this.map,
    required this.initialPose,
    required this.goal,
    required this.patrolWaypoints,
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
    _drawPatrolRoute(canvas, size, current);
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

  void _drawPatrolRoute(Canvas canvas, Size size, SlamMap map) {
    if (patrolWaypoints.isEmpty) return;
    final routePaint = Paint()
      ..color = const Color(0xFF8A5CF6)
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    final markerPaint = Paint()..color = const Color(0xFF8A5CF6);
    final textPainter = TextPainter(
      textDirection: TextDirection.ltr,
      textAlign: TextAlign.center,
    );
    final path = Path();
    var started = false;
    for (final point in patrolWaypoints) {
      if (!_pointInsideMap(point, map)) continue;
      final p = _mapToCanvas(point, size, map);
      if (!started) {
        path.moveTo(p.dx, p.dy);
        started = true;
      } else {
        path.lineTo(p.dx, p.dy);
      }
    }
    canvas.drawPath(path, routePaint);

    for (var i = 0; i < patrolWaypoints.length; i++) {
      final point = patrolWaypoints[i];
      if (!_pointInsideMap(point, map)) continue;
      final p = _mapToCanvas(point, size, map);
      canvas.drawCircle(p, 10, markerPaint);
      textPainter.text = TextSpan(
        text: '${i + 1}',
        style: const TextStyle(
          color: Colors.white,
          fontSize: 11,
          fontWeight: FontWeight.w700,
        ),
      );
      textPainter.layout(minWidth: 20, maxWidth: 20);
      textPainter.paint(canvas, p - const Offset(10, 7));
      _drawArrow(
        canvas,
        p,
        point.yaw,
        22,
        Paint()
          ..color = const Color(0xFF8A5CF6)
          ..strokeWidth = 3
          ..strokeCap = StrokeCap.round,
      );
    }
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
        oldDelegate.patrolWaypoints != patrolWaypoints ||
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
