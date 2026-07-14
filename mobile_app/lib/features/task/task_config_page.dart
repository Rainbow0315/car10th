import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../data/repository.dart';

class TaskConfigPage extends StatefulWidget {
  const TaskConfigPage({super.key});

  @override
  State<TaskConfigPage> createState() => _TaskConfigPageState();
}

class _TaskConfigPageState extends State<TaskConfigPage> {
  late Future<List<PatrolTask>> _tasksFuture;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    final repo = context.read<Repository>();
    _tasksFuture = repo.listPatrolTasks();
  }

  Future<void> _refresh() async {
    setState(_reload);
    await _tasksFuture;
  }

  Future<void> _editTask([PatrolTask? task]) async {
    final result = await showDialog<_PatrolTaskDraft>(
      context: context,
      builder: (context) => _PatrolTaskDialog(initial: task),
    );
    if (result == null) return;
    if (!mounted) return;
    final repo = context.read<Repository>();
    if (result.taskCode == null) {
      await repo.createPatrolTask(
        name: result.name,
        robotCode: result.robotCode,
        waypoints: result.waypoints,
        loopCount: result.loopCount,
        scheduleCron: result.scheduleCron,
      );
    } else {
      await repo.updatePatrolTask(
        PatrolTask(
          taskCode: result.taskCode!,
          name: result.name,
          robotCode: result.robotCode,
          waypoints: result.waypoints,
          loopCount: result.loopCount,
          scheduleCron: result.scheduleCron,
          status: task?.status ?? 'draft',
        ),
      );
    }
    await _refresh();
  }

  Future<void> _deleteTask(String taskCode) async {
    await context.read<Repository>().deletePatrolTask(taskCode);
    if (!mounted) return;
    await _refresh();
  }

  Future<void> _startTask(String taskCode) async {
    await context.read<Repository>().startPatrolTask(taskCode);
    if (!mounted) return;
    await _refresh();
  }

  Future<void> _stopTask(String taskCode) async {
    await context.read<Repository>().stopPatrolTask(taskCode);
    if (!mounted) return;
    await _refresh();
  }

  Future<void> _showRuntime(String taskCode) async {
    try {
      final runtime =
          await context.read<Repository>().getPatrolRuntime(taskCode);
      if (!mounted) return;
      final message = runtime == null
          ? '暂无运行态（可能未启动或后端已重启）'
          : 'state=${runtime.state} running=${runtime.running} seq=${runtime.currentSeq ?? "-"} ${runtime.message ?? ""}';
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('读取运行态失败：$e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('巡检任务配置')),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('巡航配置', style: theme.textTheme.titleSmall),
                    const SizedBox(height: 8),
                    const _KvRow(k: '路线来源', v: '航点顺序即巡航路线'),
                    const _KvRow(k: '定时格式', v: 'cron，例如 0 22 * * *'),
                    const _KvRow(k: '执行链路', v: 'App -> web_api -> /goal_pose'),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 10,
                      runSpacing: 8,
                      children: [
                        FilledButton.icon(
                          onPressed: () => _editTask(),
                          icon: const Icon(Icons.route_outlined),
                          label: const Text('设置巡航路线'),
                        ),
                        FilledButton.tonalIcon(
                          onPressed: () => _editTask(),
                          icon: const Icon(Icons.schedule),
                          label: const Text('设置定时巡航'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            FutureBuilder<List<PatrolTask>>(
              future: _tasksFuture,
              builder: (context, snapshot) {
                if (!snapshot.hasData) {
                  return const Center(
                    child: Padding(
                      padding: EdgeInsets.all(24),
                      child: CircularProgressIndicator(),
                    ),
                  );
                }
                final list = snapshot.data!;
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text('巡航任务', style: theme.textTheme.titleSmall),
                            IconButton(
                              onPressed: () => _editTask(),
                              icon: const Icon(Icons.add),
                              tooltip: '新增任务',
                            ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        if (list.isEmpty)
                          Text('暂无任务', style: theme.textTheme.bodyMedium)
                        else
                          ...list.map(
                            (t) => Column(
                              children: [
                                ListTile(
                                  contentPadding: EdgeInsets.zero,
                                  title: Text(t.name),
                                  subtitle: Text(
                                    'robot=${t.robotCode} 航点=${t.waypoints.length} loop=${t.loopCount} 定时=${t.scheduleCron?.isNotEmpty == true ? t.scheduleCron : "手动"} status=${t.status}',
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  trailing: Wrap(
                                    spacing: 6,
                                    children: [
                                      IconButton(
                                        onPressed: () =>
                                            _showRuntime(t.taskCode),
                                        icon: const Icon(Icons.info_outline),
                                      ),
                                      IconButton(
                                        onPressed: () => _editTask(t),
                                        icon: const Icon(Icons.edit_outlined),
                                      ),
                                      IconButton(
                                        onPressed: () =>
                                            _deleteTask(t.taskCode),
                                        icon: const Icon(Icons.delete_outline),
                                      ),
                                    ],
                                  ),
                                ),
                                Row(
                                  children: [
                                    Expanded(
                                      child: FilledButton.tonalIcon(
                                        onPressed: () => _startTask(t.taskCode),
                                        icon: const Icon(Icons.play_arrow),
                                        label: const Text('启动巡航'),
                                      ),
                                    ),
                                    const SizedBox(width: 10),
                                    Expanded(
                                      child: OutlinedButton.icon(
                                        onPressed: () => _stopTask(t.taskCode),
                                        icon: const Icon(Icons.stop),
                                        label: const Text('停止巡航'),
                                      ),
                                    ),
                                  ],
                                ),
                                const Divider(height: 18),
                              ],
                            ),
                          ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _PatrolTaskDraft {
  final String? taskCode;
  final String name;
  final String robotCode;
  final int loopCount;
  final String? scheduleCron;
  final List<PatrolWaypointConfig> waypoints;

  const _PatrolTaskDraft({
    required this.taskCode,
    required this.name,
    required this.robotCode,
    required this.loopCount,
    required this.scheduleCron,
    required this.waypoints,
  });
}

class _PatrolTaskDialog extends StatefulWidget {
  final PatrolTask? initial;

  const _PatrolTaskDialog({required this.initial});

  @override
  State<_PatrolTaskDialog> createState() => _PatrolTaskDialogState();
}

class _PatrolTaskDialogState extends State<_PatrolTaskDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name;
  late final TextEditingController _robotCode;
  late final TextEditingController _loopCount;
  late final TextEditingController _scheduleCron;
  late List<PatrolWaypointConfig> _waypoints;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.initial?.name ?? '');
    _robotCode =
        TextEditingController(text: widget.initial?.robotCode ?? 'robot_001');
    _loopCount = TextEditingController(
        text: (widget.initial?.loopCount ?? 1).toString());
    _scheduleCron =
        TextEditingController(text: widget.initial?.scheduleCron ?? '');
    _waypoints =
        List<PatrolWaypointConfig>.from(widget.initial?.waypoints ?? const []);
    _normalizeSeq();
  }

  @override
  void dispose() {
    _name.dispose();
    _robotCode.dispose();
    _loopCount.dispose();
    _scheduleCron.dispose();
    super.dispose();
  }

  void _normalizeSeq() {
    _waypoints = _waypoints
        .asMap()
        .entries
        .map((e) => PatrolWaypointConfig(
            seq: e.key + 1, name: e.value.name, point: e.value.point))
        .toList(growable: false);
  }

  Future<void> _addWaypoint([PatrolWaypointConfig? initial]) async {
    final result = await showDialog<PatrolWaypointConfig>(
      context: context,
      builder: (context) => _PatrolWaypointDialog(initial: initial),
    );
    if (result == null) return;
    setState(() {
      if (initial == null) {
        _waypoints = [..._waypoints, result];
      } else {
        final idx = _waypoints.indexWhere((w) => w.seq == initial.seq);
        if (idx >= 0) {
          final updated = PatrolWaypointConfig(
              seq: _waypoints[idx].seq, name: result.name, point: result.point);
          _waypoints = [..._waypoints]..[idx] = updated;
        }
      }
      _normalizeSeq();
    });
  }

  void _removeWaypoint(int seq) {
    setState(() {
      _waypoints =
          _waypoints.where((w) => w.seq != seq).toList(growable: false);
      _normalizeSeq();
    });
  }

  void _moveWaypoint(int index, int delta) {
    final next = index + delta;
    if (next < 0 || next >= _waypoints.length) return;
    setState(() {
      final list = [..._waypoints];
      final tmp = list[index];
      list[index] = list[next];
      list[next] = tmp;
      _waypoints = list;
      _normalizeSeq();
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.initial == null ? '新增巡航任务' : '编辑巡航任务'),
      content: SizedBox(
        width: 520,
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                controller: _name,
                decoration: const InputDecoration(
                    labelText: '任务名称', border: OutlineInputBorder()),
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? '请输入任务名称' : null,
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _robotCode,
                      decoration: const InputDecoration(
                          labelText: 'robot_code',
                          border: OutlineInputBorder()),
                      validator: (v) => (v == null || v.trim().isEmpty)
                          ? '请输入 robot_code'
                          : null,
                    ),
                  ),
                  const SizedBox(width: 10),
                  SizedBox(
                    width: 120,
                    child: TextFormField(
                      controller: _loopCount,
                      decoration: const InputDecoration(
                          labelText: '循环次数', border: OutlineInputBorder()),
                      keyboardType: TextInputType.number,
                      validator: (v) =>
                          int.tryParse(v ?? '') == null ? '无效' : null,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              TextFormField(
                controller: _scheduleCron,
                decoration: const InputDecoration(
                  labelText: '定时 cron（可空）',
                  hintText: '0 22 * * *',
                  border: OutlineInputBorder(),
                ),
                validator: (v) {
                  final clean = v?.trim() ?? '';
                  if (clean.isEmpty) return null;
                  return clean.split(RegExp(r'\s+')).length == 5
                      ? null
                      : 'cron 需要 5 段，例如 0 22 * * *';
                },
              ),
              const SizedBox(height: 10),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('航点（顺序即执行顺序）'),
                  IconButton(
                      onPressed: () => _addWaypoint(),
                      icon: const Icon(Icons.add)),
                ],
              ),
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 260),
                child: ListView(
                  shrinkWrap: true,
                  children: _waypoints
                      .asMap()
                      .entries
                      .map(
                        (e) => ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(
                              '${e.value.seq}. ${e.value.name.isEmpty ? "航点" : e.value.name}'),
                          subtitle: Text(
                            '(${e.value.point.x.toStringAsFixed(2)}, ${e.value.point.y.toStringAsFixed(2)}) yaw=${e.value.point.yaw.toStringAsFixed(2)}',
                          ),
                          trailing: Wrap(
                            spacing: 4,
                            children: [
                              IconButton(
                                onPressed: () => _moveWaypoint(e.key, -1),
                                icon: const Icon(Icons.arrow_upward),
                              ),
                              IconButton(
                                onPressed: () => _moveWaypoint(e.key, 1),
                                icon: const Icon(Icons.arrow_downward),
                              ),
                              IconButton(
                                onPressed: () => _addWaypoint(e.value),
                                icon: const Icon(Icons.edit_outlined),
                              ),
                              IconButton(
                                onPressed: () => _removeWaypoint(e.value.seq),
                                icon: const Icon(Icons.delete_outline),
                              ),
                            ],
                          ),
                        ),
                      )
                      .toList(),
                ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('取消')),
        FilledButton(
          onPressed: () {
            final ok = _formKey.currentState?.validate() ?? false;
            if (!ok) return;
            if (_waypoints.length < 2) {
              ScaffoldMessenger.of(context)
                  .showSnackBar(const SnackBar(content: Text('至少需要 2 个航点')));
              return;
            }
            final loopCount = int.tryParse(_loopCount.text) ?? 1;
            Navigator.of(context).pop(
              _PatrolTaskDraft(
                taskCode: widget.initial?.taskCode,
                name: _name.text.trim(),
                robotCode: _robotCode.text.trim(),
                loopCount: loopCount,
                scheduleCron: _scheduleCron.text.trim().isEmpty
                    ? null
                    : _scheduleCron.text.trim(),
                waypoints: _waypoints,
              ),
            );
          },
          child: const Text('保存'),
        ),
      ],
    );
  }
}

class _PatrolWaypointDialog extends StatefulWidget {
  final PatrolWaypointConfig? initial;

  const _PatrolWaypointDialog({required this.initial});

  @override
  State<_PatrolWaypointDialog> createState() => _PatrolWaypointDialogState();
}

class _PatrolWaypointDialogState extends State<_PatrolWaypointDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name;
  late final TextEditingController _x;
  late final TextEditingController _y;
  late final TextEditingController _yaw;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.initial?.name ?? '');
    _x = TextEditingController(text: widget.initial?.point.x.toString() ?? '0');
    _y = TextEditingController(text: widget.initial?.point.y.toString() ?? '0');
    _yaw = TextEditingController(
        text: widget.initial?.point.yaw.toString() ?? '0');
  }

  @override
  void dispose() {
    _name.dispose();
    _x.dispose();
    _y.dispose();
    _yaw.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.initial == null ? '新增航点' : '编辑航点'),
      content: SizedBox(
        width: 420,
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                controller: _name,
                decoration: const InputDecoration(
                    labelText: '名称', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _x,
                      decoration: const InputDecoration(
                          labelText: 'X', border: OutlineInputBorder()),
                      keyboardType: TextInputType.number,
                      validator: (v) =>
                          double.tryParse(v ?? '') == null ? '无效' : null,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: TextFormField(
                      controller: _y,
                      decoration: const InputDecoration(
                          labelText: 'Y', border: OutlineInputBorder()),
                      keyboardType: TextInputType.number,
                      validator: (v) =>
                          double.tryParse(v ?? '') == null ? '无效' : null,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              TextFormField(
                controller: _yaw,
                decoration: const InputDecoration(
                    labelText: 'Yaw(rad)', border: OutlineInputBorder()),
                keyboardType: TextInputType.number,
                validator: (v) =>
                    double.tryParse(v ?? '') == null ? '无效' : null,
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('取消')),
        FilledButton(
          onPressed: () {
            final ok = _formKey.currentState?.validate() ?? false;
            if (!ok) return;
            Navigator.of(context).pop(
              PatrolWaypointConfig(
                seq: widget.initial?.seq ?? 1,
                name: _name.text.trim(),
                point: MapPoint(
                  x: double.parse(_x.text),
                  y: double.parse(_y.text),
                  yaw: double.parse(_yaw.text),
                ),
              ),
            );
          },
          child: const Text('保存'),
        ),
      ],
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
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(k, style: theme.textTheme.bodyMedium),
          Text(
            v,
            style: theme.textTheme.bodyMedium
                ?.copyWith(fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}
