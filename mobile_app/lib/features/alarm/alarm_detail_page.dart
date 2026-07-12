import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app/session.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import 'alarm_labels.dart';

class AlarmDetailPage extends StatefulWidget {
  final String alarmId;

  const AlarmDetailPage({
    super.key,
    required this.alarmId,
  });

  @override
  State<AlarmDetailPage> createState() => _AlarmDetailPageState();
}

class _AlarmDetailPageState extends State<AlarmDetailPage> {
  late Future<AlarmEvent?> _future;
  final _remark = TextEditingController();
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _future = context.read<Repository>().getAlarmById(widget.alarmId);
  }

  @override
  void dispose() {
    _remark.dispose();
    super.dispose();
  }

  Future<void> _handle(AlarmEvent alarm) async {
    final remark = _remark.text.trim();
    if (remark.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('请填写处理说明')),
      );
      return;
    }

    setState(() => _saving = true);
    try {
      final updated = await context
          .read<Repository>()
          .markAlarmHandled(id: alarm.id, remark: remark);
      if (!mounted) return;
      setState(() => _future = Future.value(updated));
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('告警已标记为已处理')),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final canHandle = context.watch<AppSession>().canHandleAlarm();

    return Scaffold(
      appBar: AppBar(title: const Text('告警详情')),
      body: FutureBuilder<AlarmEvent?>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }

          final alarm = snapshot.data;
          if (alarm == null) {
            return Center(child: Text('未找到告警：${widget.alarmId}'));
          }
          if (_remark.text.isEmpty) _remark.text = alarm.remark ?? '';

          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
            children: [
              _AlarmImage(imagePath: alarm.imagePath),
              const SizedBox(height: 12),
              _InfoSection(
                title: '检测信息',
                rows: [
                  _InfoRow('告警类型', alarmTypeLabel(alarm.type)),
                  _InfoRow('风险等级', alarmRiskLabel(alarm.risk)),
                  _InfoRow(
                    '置信度',
                    '${(alarm.confidence * 100).toStringAsFixed(1)}%',
                  ),
                  _InfoRow('处理状态', alarmStatusLabel(alarm.status)),
                  _InfoRow('检测时间', alarm.timestamp.toLocal().toString()),
                  _InfoRow('检测模型', alarm.detectionModel ?? '-'),
                  _InfoRow('识别标签', alarm.detectionLabel ?? '-'),
                  _InfoRow('边界框', _bboxText(alarm.bbox)),
                ],
              ),
              const SizedBox(height: 12),
              _InfoSection(
                title: '来源位置',
                rows: [
                  _InfoRow('小车编号', alarm.robotCode ?? '-'),
                  _InfoRow('相机编号', alarm.cameraCode ?? '-'),
                  _InfoRow(
                    '坐标',
                    'x=${alarm.point.x.toStringAsFixed(2)}, y=${alarm.point.y.toStringAsFixed(2)}',
                  ),
                  _InfoRow(
                    '朝向',
                    '${alarm.point.yaw.toStringAsFixed(2)} rad',
                  ),
                  _InfoRow(
                      '截图路径', alarm.imagePath.isEmpty ? '-' : alarm.imagePath),
                ],
              ),
              const SizedBox(height: 12),
              _HandleSection(
                alarm: alarm,
                controller: _remark,
                saving: _saving,
                canHandle: canHandle,
                onSubmit: () => _handle(alarm),
              ),
            ],
          );
        },
      ),
    );
  }

  String _bboxText(List<double> bbox) {
    if (bbox.isEmpty) return '-';
    return bbox.map((v) => v.toStringAsFixed(1)).join(', ');
  }
}

class _AlarmImage extends StatelessWidget {
  final String imagePath;

  const _AlarmImage({required this.imagePath});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final uri = Uri.tryParse(imagePath);
    Widget image;

    if (uri != null && (uri.scheme == 'http' || uri.scheme == 'https')) {
      image = Image.network(
        imagePath,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => _ImageFallback(path: imagePath),
      );
    } else {
      final file = File(imagePath);
      image = imagePath.isNotEmpty && file.existsSync()
          ? Image.file(file, fit: BoxFit.cover)
          : _ImageFallback(path: imagePath);
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: ColoredBox(
        color: colors.surfaceContainerLow,
        child: AspectRatio(
          aspectRatio: 16 / 9,
          child: image,
        ),
      ),
    );
  }
}

class _ImageFallback extends StatelessWidget {
  final String path;

  const _ImageFallback({required this.path});

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
            Icon(Icons.image_not_supported_outlined,
                size: 44, color: colors.onSurfaceVariant),
            const SizedBox(height: 8),
            Text(
              path.isEmpty ? '暂无风险截图' : '截图暂不可用',
              style: theme.textTheme.bodyMedium,
            ),
            if (path.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                path,
                maxLines: 1,
                softWrap: false,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: colors.onSurfaceVariant),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _InfoSection extends StatelessWidget {
  final String title;
  final List<_InfoRow> rows;

  const _InfoSection({
    required this.title,
    required this.rows,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            ...rows,
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;

  const _InfoRow(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          SizedBox(
            width: 76,
            child: Text(
              label,
              maxLines: 1,
              softWrap: false,
              style: theme.textTheme.bodyMedium,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              value,
              maxLines: 1,
              softWrap: false,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodyMedium
                  ?.copyWith(fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}

class _HandleSection extends StatelessWidget {
  final AlarmEvent alarm;
  final TextEditingController controller;
  final bool saving;
  final bool canHandle;
  final VoidCallback onSubmit;

  const _HandleSection({
    required this.alarm,
    required this.controller,
    required this.saving,
    required this.canHandle,
    required this.onSubmit,
  });

  @override
  Widget build(BuildContext context) {
    final handled = alarm.status == AlarmStatus.handled;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('处理记录', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 10),
            TextField(
              controller: controller,
              enabled: canHandle && !handled && !saving,
              maxLines: 3,
              decoration: const InputDecoration(
                labelText: '处理说明',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: (!canHandle || handled || saving) ? null : onSubmit,
              icon: saving
                  ? const SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.check_circle_outline),
              label: Text(handled ? '已处理' : '标记为已处理'),
            ),
          ],
        ),
      ),
    );
  }
}
