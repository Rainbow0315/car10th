import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app/app_settings.dart';
import '../../data/models.dart';
import '../../data/repository.dart';

class CameraYoloCard extends StatefulWidget {
  final String title;

  const CameraYoloCard({
    super.key,
    this.title = '监测监控',
  });

  @override
  State<CameraYoloCard> createState() => _CameraYoloCardState();
}

class _CameraYoloCardState extends State<CameraYoloCard> {
  static const _cameraCode = 'usb_cam';
  static const _cameraTopic = '/image_raw';

  bool _previewRunning = false;
  Future<InspectionMonitorStatus>? _monitorFuture;
  bool _monitorBusy = false;
  bool _loaded = false;
  String _robotCode = 'robot_001';
  int _previewSession = 0;

  Repository get _repo => context.read<Repository>();
  AppSettings get _settings => context.read<AppSettings>();

  RobotControlTarget get _target {
    return _settings.controlTargets.firstWhere(
      (target) => target.code == _robotCode,
      orElse: () => _settings.controlTargets.first,
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_loaded) return;
    _loaded = true;
    final settings = context.read<AppSettings>();
    _robotCode = settings.selectedControlTarget.code;
    _robotCode = settings.controlTargets.any(
      (target) => target.code == _robotCode,
    )
        ? _robotCode
        : settings.selectedControlTarget.code;
    _monitorFuture = _repo.getInspectionMonitorStatus(
      baseUrl: _target.apiBaseUrl,
    );
  }

  void _togglePreview() {
    setState(() {
      _previewRunning = !_previewRunning;
      if (_previewRunning) _previewSession++;
    });
  }

  void _refreshMonitorStatus() {
    setState(() {
      _monitorFuture = _repo.getInspectionMonitorStatus(
        baseUrl: _target.apiBaseUrl,
      );
    });
  }

  void _selectRobot(String robotCode) {
    if (_robotCode == robotCode) return;
    setState(() {
      _robotCode = robotCode;
      _previewRunning = false;
      _monitorFuture = _repo.getInspectionMonitorStatus(
        baseUrl: _target.apiBaseUrl,
      );
    });
  }

  Future<void> _setMonitorRunning(bool running) async {
    setState(() => _monitorBusy = true);
    try {
      final status = running
          ? await _repo.startInspectionMonitor(
              topicName: _cameraTopic,
              robotCode: _target.code,
              cameraCode: _cameraCode,
              baseUrl: _target.apiBaseUrl,
            )
          : await _repo.stopInspectionMonitor(baseUrl: _target.apiBaseUrl);
      if (!mounted) return;
      setState(() {
        _monitorFuture = Future.value(status);
      });
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('检测操作失败：${_shortMessage(error)}'),
          duration: const Duration(seconds: 5),
        ),
      );
    } finally {
      if (mounted) setState(() => _monitorBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final settings = context.watch<AppSettings>();
    final targets = settings.controlTargets;
    final selected = targets.firstWhere(
      (target) => target.code == _robotCode,
      orElse: () => targets.first,
    );
    final streamUrl = _repo.cameraMjpegUrl(
      topicName: _cameraTopic,
      fps: 5.0,
      baseUrl: selected.apiBaseUrl,
    );
    final snapshotUrl = _repo.cameraSnapshotUrl(
      topicName: _cameraTopic,
      cacheBust: DateTime.now().millisecondsSinceEpoch,
      baseUrl: selected.apiBaseUrl,
    );

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.video_camera_back_outlined, color: colors.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(widget.title, style: theme.textTheme.titleMedium),
                ),
                IconButton(
                  tooltip: '刷新',
                  onPressed: _refreshMonitorStatus,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    key: ValueKey('monitor-robot-${selected.code}'),
                    initialValue: selected.code,
                    isDense: true,
                    decoration: const InputDecoration(
                      labelText: '小车',
                      prefixIcon: Icon(Icons.directions_car_outlined),
                    ),
                    items: [
                      for (final target in targets)
                        DropdownMenuItem(
                          value: target.code,
                          child: Text(target.label),
                        ),
                    ],
                    onChanged: _monitorBusy
                        ? null
                        : (value) {
                            if (value != null) _selectRobot(value);
                          },
                  ),
                ),
                const SizedBox(width: 10),
                const Chip(
                  avatar: Icon(Icons.videocam_outlined),
                  label: Text('USB'),
                ),
              ],
            ),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: AspectRatio(
                aspectRatio: 16 / 9,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: colors.surfaceContainerHighest,
                    border: Border.all(color: colors.outlineVariant),
                  ),
                  child: _previewRunning
                      ? _MjpegStreamView(
                          key: ValueKey(
                            '${selected.code}-$_cameraCode-$_previewSession',
                          ),
                          url: streamUrl,
                          fallbackSnapshotUrl: snapshotUrl,
                          fit: BoxFit.cover,
                        )
                      : const _CameraPlaceholder(
                          icon: Icons.videocam_outlined,
                          text: '预览已停止',
                        ),
                ),
              ),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                FilledButton.tonalIcon(
                  onPressed: _togglePreview,
                  icon: Icon(
                    _previewRunning
                        ? Icons.videocam_off_outlined
                        : Icons.videocam_outlined,
                  ),
                  label: Text(_previewRunning ? '停止预览' : '开始预览'),
                ),
                FutureBuilder<InspectionMonitorStatus>(
                  future: _monitorFuture,
                  builder: (context, snapshot) {
                    final status = snapshot.data;
                    final running = status?.running ?? false;
                    return FilledButton.icon(
                      onPressed: _monitorBusy
                          ? null
                          : () => unawaited(_setMonitorRunning(!running)),
                      icon: Icon(
                        running
                            ? Icons.pause_circle_outline
                            : Icons.play_circle_outline,
                      ),
                      label: Text(running ? '停止检测' : '开始检测'),
                    );
                  },
                ),
              ],
            ),
            const SizedBox(height: 10),
            FutureBuilder<InspectionMonitorStatus>(
              future: _monitorFuture,
              builder: (context, snapshot) {
                if (snapshot.hasError) {
                  return Text(
                    '状态读取失败',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: colors.error,
                    ),
                  );
                }
                final status = snapshot.data;
                if (status == null) {
                  return Text('正在读取状态', style: theme.textTheme.bodySmall);
                }
                return Column(
                  children: [
                    _KvRow(k: '检测', v: status.running ? '运行中' : '已停止'),
                    _KvRow(k: '帧数', v: '${status.totalFrames}'),
                    _KvRow(k: '最近', v: _formatTime(status.lastCheckedAt)),
                    if (status.lastError?.isNotEmpty == true)
                      _KvRow(k: '错误', v: status.lastError!),
                  ],
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  String _formatTime(DateTime? value) {
    if (value == null) return '-';
    return '${value.hour.toString().padLeft(2, '0')}:'
        '${value.minute.toString().padLeft(2, '0')}:'
        '${value.second.toString().padLeft(2, '0')}';
  }

  String _shortMessage(Object error) {
    final clean = error.toString().replaceAll(RegExp(r'\s+'), ' ').trim();
    if (clean.length <= 180) return clean;
    return '${clean.substring(0, 180)}...';
  }
}

class _CameraPlaceholder extends StatelessWidget {
  final IconData icon;
  final String text;

  const _CameraPlaceholder({
    required this.icon,
    required this.text,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 34, color: colors.onSurfaceVariant),
            const SizedBox(height: 8),
            Text(text, style: theme.textTheme.titleSmall),
          ],
        ),
      ),
    );
  }
}

class _MjpegStreamView extends StatefulWidget {
  final String url;
  final String fallbackSnapshotUrl;
  final BoxFit fit;

  const _MjpegStreamView({
    super.key,
    required this.url,
    required this.fallbackSnapshotUrl,
    required this.fit,
  });

  @override
  State<_MjpegStreamView> createState() => _MjpegStreamViewState();
}

class _MjpegStreamViewState extends State<_MjpegStreamView> {
  static const _maxBufferBytes = 2 * 1024 * 1024;

  final List<int> _buffer = <int>[];
  HttpClient? _client;
  StreamSubscription<List<int>>? _subscription;
  Timer? _fallbackTimer;
  Uint8List? _frame;
  String? _error;
  bool _connecting = false;
  int _fallbackTick = 0;

  @override
  void initState() {
    super.initState();
    _start();
  }

  @override
  void didUpdateWidget(covariant _MjpegStreamView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.url != widget.url) {
      _restart();
    }
  }

  Future<void> _restart() async {
    await _stop();
    if (mounted) _start();
  }

  Future<void> _start() async {
    if (_connecting) return;
    setState(() {
      _connecting = true;
      _error = null;
    });

    final client = HttpClient();
    _client = client;
    try {
      final request = await client.getUrl(Uri.parse(widget.url));
      request.headers
          .set(HttpHeaders.acceptHeader, 'multipart/x-mixed-replace');
      final response =
          await request.close().timeout(const Duration(seconds: 8));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw HttpException('HTTP ${response.statusCode}');
      }
      if (!mounted || !identical(_client, client)) return;
      setState(() => _connecting = false);
      _subscription = response.listen(
        _handleChunk,
        onError: (Object error) {
          _markError(error.toString());
        },
        onDone: () {
          if (mounted && _error == null) {
            _markError('连接已关闭');
          }
        },
        cancelOnError: true,
      );
    } catch (error) {
      client.close(force: true);
      if (!mounted || !identical(_client, client)) return;
      setState(() => _connecting = false);
      _markError(error.toString());
    }
  }

  void _markError(String message) {
    if (!mounted) return;
    _fallbackTimer ??= Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _fallbackTick++);
    });
    setState(() => _error = message);
  }

  void _handleChunk(List<int> chunk) {
    _buffer.addAll(chunk);
    if (_buffer.length > _maxBufferBytes) {
      _buffer.removeRange(0, _buffer.length - _maxBufferBytes);
    }

    while (true) {
      final start = _indexOfJpegStart(_buffer);
      if (start < 0) {
        if (_buffer.length > 1) {
          _buffer.removeRange(0, _buffer.length - 1);
        }
        return;
      }
      if (start > 0) {
        _buffer.removeRange(0, start);
      }

      final end = _indexOfJpegEnd(_buffer, 2);
      if (end < 0) return;

      final frame = Uint8List.fromList(_buffer.sublist(0, end + 2));
      _buffer.removeRange(0, end + 2);
      if (mounted) {
        _fallbackTimer?.cancel();
        _fallbackTimer = null;
        setState(() {
          _frame = frame;
          _error = null;
        });
      }
    }
  }

  int _indexOfJpegStart(List<int> bytes) {
    for (var i = 0; i < bytes.length - 1; i++) {
      if (bytes[i] == 0xFF && bytes[i + 1] == 0xD8) return i;
    }
    return -1;
  }

  int _indexOfJpegEnd(List<int> bytes, int from) {
    for (var i = from; i < bytes.length - 1; i++) {
      if (bytes[i] == 0xFF && bytes[i + 1] == 0xD9) return i;
    }
    return -1;
  }

  Future<void> _stop() async {
    _fallbackTimer?.cancel();
    _fallbackTimer = null;
    await _subscription?.cancel();
    _subscription = null;
    _client?.close(force: true);
    _client = null;
    _buffer.clear();
  }

  @override
  void dispose() {
    unawaited(_stop());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final frame = _frame;
    if (frame != null) {
      return Image.memory(
        frame,
        gaplessPlayback: true,
        fit: widget.fit,
      );
    }
    if (_error != null) {
      return Stack(
        fit: StackFit.expand,
        children: [
          Image.network(
            '${widget.fallbackSnapshotUrl}&fallback=$_fallbackTick',
            fit: widget.fit,
            gaplessPlayback: true,
            errorBuilder: (context, error, stackTrace) {
              return const _CameraPlaceholder(
                icon: Icons.videocam_off_outlined,
                text: '预览不可用',
              );
            },
            loadingBuilder: (context, child, progress) => child,
          ),
          Align(
            alignment: Alignment.topLeft,
            child: Container(
              margin: const EdgeInsets.all(8),
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.62),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                _shortError(_error!),
                style: const TextStyle(color: Colors.white, fontSize: 11),
              ),
            ),
          ),
        ],
      );
    }
    return const Center(child: CircularProgressIndicator());
  }

  String _shortError(String value) {
    final clean = value.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (clean.length <= 140) return clean;
    return '${clean.substring(0, 140)}...';
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
          Flexible(
            child: Text(
              v,
              textAlign: TextAlign.end,
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
