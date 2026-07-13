import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../data/repository.dart';
import 'alarm_detail_page.dart';
import 'alarm_labels.dart';

class AlarmListPage extends StatefulWidget {
  const AlarmListPage({super.key});

  @override
  State<AlarmListPage> createState() => _AlarmListPageState();
}

class _AlarmListPageState extends State<AlarmListPage> {
  AlarmType? _type;
  RiskLevel? _risk;
  AlarmStatus? _status;

  late Future<List<AlarmEvent>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<AlarmEvent>> _load() {
    return context
        .read<Repository>()
        .listAlarms(type: _type, risk: _risk, status: _status);
  }

  Color _riskColor(RiskLevel r, ColorScheme cs) {
    switch (r) {
      case RiskLevel.low:
        return cs.tertiary;
      case RiskLevel.medium:
        return cs.primary;
      case RiskLevel.high:
        return cs.error;
    }
  }

  void _open(AlarmEvent alarm) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => AlarmDetailPage(alarmId: alarm.id)),
    );
  }

  Future<void> _refresh() async {
    setState(() => _future = _load());
    await _future;
  }

  Future<void> _pickFilters() async {
    final picked = await showModalBottomSheet<_FilterState>(
      context: context,
      showDragHandle: true,
      builder: (context) {
        return _FilterSheet(
          initial: _FilterState(type: _type, risk: _risk, status: _status),
        );
      },
    );
    if (picked == null) return;
    setState(() {
      _type = picked.type;
      _risk = picked.risk;
      _status = picked.status;
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('告警中心'),
        actions: [
          IconButton(
            onPressed: _pickFilters,
            icon: const Icon(Icons.filter_alt_outlined),
            tooltip: '筛选告警',
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<List<AlarmEvent>>(
          future: _future,
          builder: (context, snapshot) {
            if (!snapshot.hasData) {
              return const Center(child: CircularProgressIndicator());
            }
            final list = snapshot.data!;
            if (list.isEmpty) {
              return ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Text('暂无告警', style: theme.textTheme.titleMedium),
                  const SizedBox(height: 6),
                  Text(
                    '当前没有符合条件的告警，可清空筛选条件后再查看。',
                    style: theme.textTheme.bodyMedium
                        ?.copyWith(color: cs.onSurfaceVariant),
                  ),
                ],
              );
            }

            return ListView.separated(
              padding: const EdgeInsets.all(12),
              itemCount: list.length,
              separatorBuilder: (_, __) => const SizedBox(height: 10),
              itemBuilder: (context, i) {
                final a = list[i];
                final riskColor = _riskColor(a.risk, cs);
                return Material(
                  color: cs.surfaceContainerLow,
                  borderRadius: BorderRadius.circular(8),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(8),
                    onTap: () => _open(a),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 10,
                      ),
                      child: Row(
                        children: [
                          CircleAvatar(
                            radius: 18,
                            backgroundColor: riskColor.withAlpha(46),
                            foregroundColor: riskColor,
                            child: Text(
                              alarmRiskLabel(a.risk),
                              maxLines: 1,
                              softWrap: false,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        '${alarmTypeLabel(a.type)} · ${alarmStatusLabel(a.status)}',
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        softWrap: false,
                                        style: theme.textTheme.titleSmall,
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    Text(
                                      '${(a.confidence * 100).toStringAsFixed(1)}%',
                                      maxLines: 1,
                                      softWrap: false,
                                      style: theme.textTheme.labelLarge
                                          ?.copyWith(color: riskColor),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 3),
                                Text(
                                  '${compactDateTime(a.timestamp)} · ${a.robotCode ?? '未知小车'} · ${a.cameraCode ?? '未知相机'}',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  softWrap: false,
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: cs.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 8),
                          const Icon(Icons.chevron_right),
                        ],
                      ),
                    ),
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }
}

class _FilterState {
  final AlarmType? type;
  final RiskLevel? risk;
  final AlarmStatus? status;

  const _FilterState({
    required this.type,
    required this.risk,
    required this.status,
  });
}

class _FilterSheet extends StatefulWidget {
  final _FilterState initial;

  const _FilterSheet({required this.initial});

  @override
  State<_FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends State<_FilterSheet> {
  AlarmType? _type;
  RiskLevel? _risk;
  AlarmStatus? _status;

  @override
  void initState() {
    super.initState();
    _type = widget.initial.type;
    _risk = widget.initial.risk;
    _status = widget.initial.status;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('筛选告警', style: theme.textTheme.titleMedium),
          const SizedBox(height: 10),
          DropdownButtonFormField<AlarmType?>(
            initialValue: _type,
            decoration: const InputDecoration(
                labelText: '告警类型', border: OutlineInputBorder()),
            items: [
              const DropdownMenuItem(value: null, child: Text('全部类型')),
              ...AlarmType.values.map((e) =>
                  DropdownMenuItem(value: e, child: Text(alarmTypeLabel(e)))),
            ],
            onChanged: (v) => setState(() => _type = v),
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<RiskLevel?>(
            initialValue: _risk,
            decoration: const InputDecoration(
                labelText: '风险等级', border: OutlineInputBorder()),
            items: [
              const DropdownMenuItem(value: null, child: Text('全部等级')),
              ...RiskLevel.values.map((e) =>
                  DropdownMenuItem(value: e, child: Text(alarmRiskLabel(e)))),
            ],
            onChanged: (v) => setState(() => _risk = v),
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<AlarmStatus?>(
            initialValue: _status,
            decoration: const InputDecoration(
                labelText: '处理状态', border: OutlineInputBorder()),
            items: [
              const DropdownMenuItem(value: null, child: Text('全部状态')),
              ...AlarmStatus.values.map((e) =>
                  DropdownMenuItem(value: e, child: Text(alarmStatusLabel(e)))),
            ],
            onChanged: (v) => setState(() => _status = v),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => setState(() {
                    _type = null;
                    _risk = null;
                    _status = null;
                  }),
                  child: const Text('清空'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton(
                  onPressed: () => Navigator.of(context).pop(
                      _FilterState(type: _type, risk: _risk, status: _status)),
                  child: const Text('应用'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}
