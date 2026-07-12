import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app/session.dart';
import '../../data/models.dart';
import '../../data/repository.dart';

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
        const SnackBar(content: Text('Please enter a handling note')),
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
        const SnackBar(content: Text('Alarm marked as handled')),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final canHandle = context.watch<AppSession>().canHandleAlarm();

    return Scaffold(
      appBar: AppBar(title: const Text('Alarm detail')),
      body: FutureBuilder<AlarmEvent?>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          final alarm = snapshot.data;
          if (alarm == null) {
            return Center(child: Text('Alarm not found: ${widget.alarmId}'));
          }
          if (_remark.text.isEmpty) _remark.text = alarm.remark ?? '';

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                clipBehavior: Clip.antiAlias,
                child: SizedBox(
                  height: 220,
                  child: _AlarmImage(imagePath: alarm.imagePath),
                ),
              ),
              const SizedBox(height: 12),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Detection', style: theme.textTheme.titleSmall),
                      const SizedBox(height: 8),
                      _KvRow(k: 'Type', v: _typeLabel(alarm.type)),
                      _KvRow(k: 'Risk', v: _riskLabel(alarm.risk)),
                      _KvRow(
                          k: 'Confidence',
                          v: '${(alarm.confidence * 100).toStringAsFixed(1)}%'),
                      _KvRow(k: 'Robot', v: alarm.robotCode ?? '-'),
                      _KvRow(k: 'Camera', v: alarm.cameraCode ?? '-'),
                      _KvRow(k: 'Model', v: alarm.detectionModel ?? '-'),
                      _KvRow(k: 'Label', v: alarm.detectionLabel ?? '-'),
                      _KvRow(
                          k: 'BBox',
                          v: alarm.bbox
                              .map((v) => v.toStringAsFixed(1))
                              .join(', ')),
                      _KvRow(
                          k: 'Time', v: alarm.timestamp.toLocal().toString()),
                      _KvRow(
                        k: 'Position',
                        v: '(${alarm.point.x.toStringAsFixed(2)}, ${alarm.point.y.toStringAsFixed(2)})',
                      ),
                      _KvRow(
                        k: 'Status',
                        v: alarm.status == AlarmStatus.handled
                            ? 'Handled'
                            : 'Pending',
                      ),
                      _KvRow(
                          k: 'Image',
                          v: alarm.imagePath.isEmpty ? '-' : alarm.imagePath),
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
                      Text('Handling', style: theme.textTheme.titleSmall),
                      const SizedBox(height: 10),
                      TextField(
                        controller: _remark,
                        enabled: canHandle &&
                            alarm.status != AlarmStatus.handled &&
                            !_saving,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          labelText: 'Handling note',
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 10),
                      FilledButton.icon(
                        onPressed: (!canHandle ||
                                alarm.status == AlarmStatus.handled ||
                                _saving)
                            ? null
                            : () => _handle(alarm),
                        icon: _saving
                            ? const SizedBox(
                                height: 18,
                                width: 18,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.check_circle_outline),
                        label: const Text('Mark handled'),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  String _typeLabel(AlarmType t) {
    switch (t) {
      case AlarmType.water:
        return 'Water';
      case AlarmType.crack:
        return 'Crack';
      case AlarmType.debris:
        return 'Foreign object';
      case AlarmType.smoking:
        return 'Other';
    }
  }

  String _riskLabel(RiskLevel r) {
    switch (r) {
      case RiskLevel.low:
        return 'Low';
      case RiskLevel.medium:
        return 'Medium';
      case RiskLevel.high:
        return 'High';
    }
  }
}

class _AlarmImage extends StatelessWidget {
  final String imagePath;

  const _AlarmImage({required this.imagePath});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final uri = Uri.tryParse(imagePath);
    if (uri != null && (uri.scheme == 'http' || uri.scheme == 'https')) {
      return Image.network(imagePath, fit: BoxFit.cover);
    }

    final file = File(imagePath);
    if (imagePath.isNotEmpty && file.existsSync()) {
      return Image.file(file, fit: BoxFit.cover);
    }

    return DecoratedBox(
      decoration: BoxDecoration(color: cs.surfaceContainerLow),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.image_outlined, size: 54, color: cs.onSurfaceVariant),
              const SizedBox(height: 8),
              Text(
                imagePath.isEmpty ? 'No risk frame path' : imagePath,
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: cs.onSurfaceVariant),
                textAlign: TextAlign.center,
                maxLines: 4,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
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
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
              width: 96, child: Text(k, style: theme.textTheme.bodyMedium)),
          Expanded(
            child: Text(
              v,
              style: theme.textTheme.bodyMedium
                  ?.copyWith(fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
