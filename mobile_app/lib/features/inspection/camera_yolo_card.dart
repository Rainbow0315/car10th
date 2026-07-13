import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../data/repository.dart';

class CameraYoloCard extends StatefulWidget {
  final String title;

  const CameraYoloCard({
    super.key,
    this.title = 'Camera and YOLO',
  });

  @override
  State<CameraYoloCard> createState() => _CameraYoloCardState();
}

class _CameraYoloCardState extends State<CameraYoloCard> {
  bool _previewRunning = false;
  Future<InspectionMonitorStatus>? _monitorFuture;
  bool _monitorBusy = false;
  bool _loaded = false;

  Repository get _repo => context.read<Repository>();

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_loaded) return;
    _loaded = true;
    _monitorFuture = _repo.getInspectionMonitorStatus();
  }

  void _togglePreview() {
    setState(() => _previewRunning = !_previewRunning);
  }

  void _refreshMonitorStatus() {
    setState(() => _monitorFuture = _repo.getInspectionMonitorStatus());
  }

  Future<void> _setMonitorRunning(bool running) async {
    setState(() => _monitorBusy = true);
    try {
      final status = running
          ? await _repo.startInspectionMonitor()
          : await _repo.stopInspectionMonitor();
      if (!mounted) return;
      setState(() => _monitorFuture = Future.value(status));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('YOLO monitor operation failed: $e'),
          duration: const Duration(seconds: 4),
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
    final streamUrl = _repo.cameraMjpegUrl(fps: 5.0);
    final snapshotUrl = _repo.cameraSnapshotUrl(
      cacheBust: DateTime.now().millisecondsSinceEpoch,
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
                  tooltip: 'Refresh YOLO status',
                  onPressed: _refreshMonitorStatus,
                  icon: const Icon(Icons.refresh),
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
                          url: streamUrl,
                          fallbackSnapshotUrl: snapshotUrl,
                          fit: BoxFit.cover,
                        )
                      : const _CameraPlaceholder(
                          icon: Icons.videocam_outlined,
                          text: 'MJPEG stream stopped',
                          detail: 'Tap below to stream /image_raw',
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
                  label: Text(
                    _previewRunning ? 'Stop preview' : 'Start preview',
                  ),
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
                      label: Text(running ? 'Stop YOLO' : 'Start YOLO'),
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
                    'YOLO status failed: ${snapshot.error}',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: colors.error,
                    ),
                  );
                }
                final status = snapshot.data;
                if (status == null) {
                  return Text(
                    'Loading YOLO status',
                    style: theme.textTheme.bodySmall,
                  );
                }
                return Column(
                  children: [
                    _KvRow(
                      k: 'YOLO',
                      v: status.running ? 'Running' : 'Stopped',
                    ),
                    _KvRow(k: 'Topic', v: status.topicName),
                    _KvRow(k: 'Frames', v: '${status.totalFrames}'),
                    _KvRow(
                        k: 'Last check', v: _formatTime(status.lastCheckedAt)),
                    if (status.lastError?.isNotEmpty == true)
                      _KvRow(k: 'Error', v: status.lastError!),
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
}

class _CameraPlaceholder extends StatelessWidget {
  final IconData icon;
  final String text;
  final String detail;

  const _CameraPlaceholder({
    required this.icon,
    required this.text,
    required this.detail,
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
            const SizedBox(height: 4),
            Text(
              detail,
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall?.copyWith(
                color: colors.onSurfaceVariant,
              ),
            ),
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
            _markError('MJPEG stream closed');
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
              return _CameraPlaceholder(
                icon: Icons.videocam_off_outlined,
                text: 'MJPEG and snapshot failed',
                detail: _shortError('MJPEG: $_error; snapshot: $error'),
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
                'MJPEG failed, fallback snapshot\n${_shortError(_error!)}',
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
