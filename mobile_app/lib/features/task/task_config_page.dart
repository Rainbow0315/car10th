import 'dart:math';

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
  late Future<List<Waypoint>> _waypointsFuture;
  late Future<List<PatrolRoute>> _routesFuture;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    final repo = context.read<Repository>();
    _waypointsFuture = repo.listWaypoints();
    _routesFuture = repo.listRoutes();
  }

  Future<void> _refresh() async {
    setState(_reload);
    await Future.wait([_waypointsFuture, _routesFuture]);
  }

  Future<void> _editWaypoint([Waypoint? waypoint]) async {
    final result = await showDialog<Waypoint>(
      context: context,
      builder: (context) => _WaypointDialog(initial: waypoint),
    );
    if (result == null) return;
    if (!mounted) return;
    await context.read<Repository>().upsertWaypoint(result);
    await _refresh();
  }

  Future<void> _deleteWaypoint(String id) async {
    await context.read<Repository>().deleteWaypoint(id);
    if (!mounted) return;
    await _refresh();
  }

  Future<void> _editRoute({
    PatrolRoute? route,
    required List<Waypoint> waypoints,
  }) async {
    final result = await showDialog<PatrolRoute>(
      context: context,
      builder: (context) => _RouteDialog(initial: route, waypoints: waypoints),
    );
    if (result == null) return;
    if (!mounted) return;
    await context.read<Repository>().upsertRoute(result);
    await _refresh();
  }

  Future<void> _deleteRoute(String id) async {
    await context.read<Repository>().deleteRoute(id);
    if (!mounted) return;
    await _refresh();
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
                    Text('定时巡检（占位）', style: theme.textTheme.titleSmall),
                    const SizedBox(height: 8),
                    const _KvRow(k: '巡检时段', v: '22:00 - 06:00'),
                    const _KvRow(k: '循环次数', v: '3'),
                    const _KvRow(k: '视觉检测', v: '开启'),
                    const SizedBox(height: 8),
                    FilledButton.tonalIcon(
                      onPressed: () => ScaffoldMessenger.of(context)
                          .showSnackBar(
                              const SnackBar(content: Text('定时巡检配置（待后端接口）'))),
                      icon: const Icon(Icons.schedule),
                      label: const Text('编辑定时配置'),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            FutureBuilder<List<Waypoint>>(
              future: _waypointsFuture,
              builder: (context, snapshot) {
                if (!snapshot.hasData)
                  return const Center(
                      child: Padding(
                          padding: EdgeInsets.all(24),
                          child: CircularProgressIndicator()));
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
                            Text('巡检航点', style: theme.textTheme.titleSmall),
                            IconButton(
                              onPressed: () => _editWaypoint(),
                              icon: const Icon(Icons.add),
                              tooltip: '新增航点',
                            ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        if (list.isEmpty)
                          Text('暂无航点', style: theme.textTheme.bodyMedium)
                        else
                          ...list.map(
                            (w) => ListTile(
                              contentPadding: EdgeInsets.zero,
                              title: Text(w.name),
                              subtitle: Text(
                                  '(${w.point.x.toStringAsFixed(2)}, ${w.point.y.toStringAsFixed(2)})'),
                              trailing: Wrap(
                                spacing: 6,
                                children: [
                                  IconButton(
                                    onPressed: () => _editWaypoint(w),
                                    icon: const Icon(Icons.edit_outlined),
                                  ),
                                  IconButton(
                                    onPressed: () => _deleteWaypoint(w.id),
                                    icon: const Icon(Icons.delete_outline),
                                  ),
                                ],
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                );
              },
            ),
            const SizedBox(height: 12),
            FutureBuilder<List<PatrolRoute>>(
              future: _routesFuture,
              builder: (context, routeSnap) {
                if (!routeSnap.hasData) return const SizedBox.shrink();
                return FutureBuilder<List<Waypoint>>(
                  future: _waypointsFuture,
                  builder: (context, wpSnap) {
                    if (!wpSnap.hasData) return const SizedBox.shrink();
                    final routes = routeSnap.data!;
                    final waypoints = wpSnap.data!;
                    final wpMap = {for (final w in waypoints) w.id: w};
                    return Card(
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text('巡逻路线', style: theme.textTheme.titleSmall),
                                IconButton(
                                  onPressed: () =>
                                      _editRoute(waypoints: waypoints),
                                  icon: const Icon(Icons.add),
                                  tooltip: '新增路线',
                                ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            if (routes.isEmpty)
                              Text('暂无路线', style: theme.textTheme.bodyMedium)
                            else
                              ...routes.map(
                                (r) => ListTile(
                                  contentPadding: EdgeInsets.zero,
                                  title: Text(r.name),
                                  subtitle: Text(
                                    r.waypointIds
                                        .map((id) => wpMap[id]?.name ?? id)
                                        .join(' -> '),
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  trailing: Wrap(
                                    spacing: 6,
                                    children: [
                                      IconButton(
                                        onPressed: () => _editRoute(
                                            route: r, waypoints: waypoints),
                                        icon: const Icon(Icons.edit_outlined),
                                      ),
                                      IconButton(
                                        onPressed: () => _deleteRoute(r.id),
                                        icon: const Icon(Icons.delete_outline),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                    );
                  },
                );
              },
            ),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('视觉模型参数（占位）', style: theme.textTheme.titleSmall),
                    const SizedBox(height: 10),
                    const Text('远程开关检测、调整置信阈值：待后端网关与 MQTT 指令协议'),
                    const SizedBox(height: 10),
                    FilledButton.tonalIcon(
                      onPressed: () => ScaffoldMessenger.of(context)
                          .showSnackBar(
                              const SnackBar(content: Text('模型参数配置（待后端接口）'))),
                      icon: const Icon(Icons.tune),
                      label: const Text('配置参数'),
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

class _WaypointDialog extends StatefulWidget {
  final Waypoint? initial;

  const _WaypointDialog({required this.initial});

  @override
  State<_WaypointDialog> createState() => _WaypointDialogState();
}

class _WaypointDialogState extends State<_WaypointDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name;
  late final TextEditingController _x;
  late final TextEditingController _y;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.initial?.name ?? '');
    _x = TextEditingController(text: widget.initial?.point.x.toString() ?? '0');
    _y = TextEditingController(text: widget.initial?.point.y.toString() ?? '0');
  }

  @override
  void dispose() {
    _name.dispose();
    _x.dispose();
    _y.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.initial == null ? '新增航点' : '编辑航点'),
      content: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextFormField(
              controller: _name,
              decoration: const InputDecoration(
                  labelText: '名称', border: OutlineInputBorder()),
              validator: (v) =>
                  (v == null || v.trim().isEmpty) ? '请输入名称' : null,
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
          ],
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
            final id = widget.initial?.id ??
                'wp_${DateTime.now().millisecondsSinceEpoch}_${Random().nextInt(999)}';
            Navigator.of(context).pop(
              Waypoint(
                id: id,
                name: _name.text.trim(),
                point: MapPoint(
                    x: double.parse(_x.text), y: double.parse(_y.text), yaw: 0),
              ),
            );
          },
          child: const Text('保存'),
        ),
      ],
    );
  }
}

class _RouteDialog extends StatefulWidget {
  final PatrolRoute? initial;
  final List<Waypoint> waypoints;

  const _RouteDialog({
    required this.initial,
    required this.waypoints,
  });

  @override
  State<_RouteDialog> createState() => _RouteDialogState();
}

class _RouteDialogState extends State<_RouteDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name;
  late final Set<String> _selected;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.initial?.name ?? '');
    _selected = widget.initial?.waypointIds.toSet() ?? <String>{};
  }

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.initial == null ? '新增路线' : '编辑路线'),
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
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? '请输入名称' : null,
              ),
              const SizedBox(height: 10),
              const Align(
                alignment: Alignment.centerLeft,
                child: Text('选择航点（顺序为暂存顺序，后续可做拖拽排序）'),
              ),
              const SizedBox(height: 6),
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 260),
                child: ListView(
                  shrinkWrap: true,
                  children: widget.waypoints
                      .map(
                        (w) => CheckboxListTile(
                          value: _selected.contains(w.id),
                          onChanged: (v) {
                            setState(() {
                              if (v == true) {
                                _selected.add(w.id);
                              } else {
                                _selected.remove(w.id);
                              }
                            });
                          },
                          title: Text(w.name),
                          subtitle: Text(
                              '(${w.point.x.toStringAsFixed(2)}, ${w.point.y.toStringAsFixed(2)})'),
                          controlAffinity: ListTileControlAffinity.leading,
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
            if (_selected.length < 2) {
              ScaffoldMessenger.of(context)
                  .showSnackBar(const SnackBar(content: Text('至少选择 2 个航点')));
              return;
            }
            final id = widget.initial?.id ??
                'rt_${DateTime.now().millisecondsSinceEpoch}_${Random().nextInt(999)}';
            Navigator.of(context).pop(
              PatrolRoute(
                id: id,
                name: _name.text.trim(),
                waypointIds: _selected.toList(),
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
          Text(v,
              style: theme.textTheme.bodyMedium
                  ?.copyWith(fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}
