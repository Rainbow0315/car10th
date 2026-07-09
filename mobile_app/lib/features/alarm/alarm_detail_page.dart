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

  String _typeLabel(AlarmType t) {
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

  String _riskLabel(RiskLevel r) {
    switch (r) {
      case RiskLevel.low:
        return '低危';
      case RiskLevel.medium:
        return '中危';
      case RiskLevel.high:
        return '高危';
    }
  }

  Future<void> _handle(AlarmEvent alarm) async {
    final remark = _remark.text.trim();
    if (remark.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('请填写处置备注')));
      return;
    }
    setState(() => _saving = true);
    try {
      final updated = await context.read<Repository>().markAlarmHandled(id: alarm.id, remark: remark);
      if (!mounted) return;
      setState(() => _future = Future.value(updated));
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('已标记为已处理')));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final canHandle = context.watch<AppSession>().canHandleAlarm();

    return Scaffold(
      appBar: AppBar(title: const Text('告警详情')),
      body: FutureBuilder<AlarmEvent?>(
        future: _future,
        builder: (context, snapshot) {
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final alarm = snapshot.data;
          if (alarm == null) {
            return Center(child: Text('未找到告警：${widget.alarmId}'));
          }
          _remark.text = alarm.remark ?? '';

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                clipBehavior: Clip.antiAlias,
                child: SizedBox(
                  height: 220,
                  child: DecoratedBox(
                    decoration: BoxDecoration(color: cs.surfaceContainerLow),
                    child: Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.image_outlined, size: 54, color: cs.onSurfaceVariant),
                          const SizedBox(height: 8),
                          Text(
                            '异常抓拍原图（后续替换为后端返回的图片 URL）',
                            style: theme.textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                            textAlign: TextAlign.center,
                          ),
                        ],
                      ),
                    ),
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
                      Text('基本信息', style: theme.textTheme.titleSmall),
                      const SizedBox(height: 8),
                      _KvRow(k: '异常类型', v: _typeLabel(alarm.type)),
                      _KvRow(k: '风险等级', v: _riskLabel(alarm.risk)),
                      _KvRow(k: '置信度', v: '${(alarm.confidence * 100).toStringAsFixed(1)}%'),
                      _KvRow(k: '发生时间', v: alarm.timestamp.toLocal().toString()),
                      _KvRow(
                        k: '地图坐标',
                        v: '(${alarm.point.x.toStringAsFixed(2)}, ${alarm.point.y.toStringAsFixed(2)})',
                      ),
                      _KvRow(k: '处理状态', v: alarm.status == AlarmStatus.handled ? '已处理' : '未处理'),
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
                      Text('运维处置', style: theme.textTheme.titleSmall),
                      const SizedBox(height: 10),
                      TextField(
                        controller: _remark,
                        enabled: canHandle && alarm.status != AlarmStatus.handled && !_saving,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          labelText: '处置备注',
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 10),
                      FilledButton.icon(
                        onPressed: (!canHandle || alarm.status == AlarmStatus.handled || _saving) ? null : () => _handle(alarm),
                        icon: _saving
                            ? const SizedBox(
                                height: 18,
                                width: 18,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.check_circle_outline),
                        label: const Text('标记已处理'),
                      ),
                      const SizedBox(height: 8),
                      OutlinedButton.icon(
                        onPressed: () => ScaffoldMessenger.of(context)
                            .showSnackBar(const SnackBar(content: Text('查看该点位历史同类异常（待后端接口）'))),
                        icon: const Icon(Icons.timeline_outlined),
                        label: const Text('查看历史同类异常'),
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
          SizedBox(width: 86, child: Text(k, style: theme.textTheme.bodyMedium)),
          Expanded(child: Text(v, style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600))),
        ],
      ),
    );
  }
}

