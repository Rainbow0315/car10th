import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/repository.dart';

class CarFindingPage extends StatefulWidget {
  const CarFindingPage({super.key});

  @override
  State<CarFindingPage> createState() => _CarFindingPageState();
}

class _CarFindingPageState extends State<CarFindingPage> {
  final _userId = TextEditingController(text: 'demo_user');
  final _plate = TextEditingController();
  bool _busy = false;
  String _status = '待操作';
  String _result = '';

  @override
  void initState() {
    super.initState();
    _loadSpots();
  }

  @override
  void dispose() {
    _userId.dispose();
    _plate.dispose();
    super.dispose();
  }

  Future<void> _loadSpots() async {
    await _run(
      '车位已加载',
      (repo) => repo.listCarFindingParkingSpots(),
      showSnack: false,
    );
  }

  Future<void> _run(
    String success,
    Future<Map<String, dynamic>> Function(Repository repo) action, {
    bool showSnack = true,
  }) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _status = '执行中';
    });
    try {
      final result = await action(context.read<Repository>());
      if (!mounted) return;
      setState(() {
        _status = success;
        _result = const JsonEncoder.withIndent('  ').convert(result);
      });
      if (showSnack) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(success)),
        );
      }
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _status = '失败';
        _result = error.toString();
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.toString())),
      );
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  String get _cleanUserId {
    final clean = _userId.text.trim();
    return clean.isEmpty ? 'demo_user' : clean;
  }

  String get _cleanPlate => _plate.text.trim();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('引导找车')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _userId,
            decoration: const InputDecoration(
              labelText: '用户 ID',
              prefixIcon: Icon(Icons.person_outline),
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _plate,
            textCapitalization: TextCapitalization.characters,
            decoration: const InputDecoration(
              labelText: '绑定车牌号',
              prefixIcon: Icon(Icons.pin_outlined),
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              FilledButton.tonalIcon(
                onPressed: _busy || _cleanPlate.isEmpty
                    ? null
                    : () => _run(
                          '车牌已绑定',
                          (repo) => repo.bindCarFindingPlate(
                            userId: _cleanUserId,
                            plateNumber: _cleanPlate,
                          ),
                        ),
                icon: const Icon(Icons.link),
                label: const Text('绑定'),
              ),
              FilledButton.tonalIcon(
                onPressed: _busy
                    ? null
                    : () => _run(
                          '已记录车位一',
                          (repo) => repo.parkCarAtSpotOne(
                            userId: _cleanUserId,
                            plateNumber:
                                _cleanPlate.isEmpty ? null : _cleanPlate,
                          ),
                        ),
                icon: const Icon(Icons.local_parking_outlined),
                label: const Text('记录车位一'),
              ),
              FilledButton.icon(
                onPressed: _busy
                    ? null
                    : () => _run(
                          '已发送导航目标',
                          (repo) => repo.guideToSpotOne(userId: _cleanUserId),
                        ),
                icon: const Icon(Icons.navigation_outlined),
                label: const Text('导航至车位一'),
              ),
              FilledButton.icon(
                onPressed: _busy
                    ? null
                    : () => _run(
                          '识别比对完成',
                          (repo) =>
                              repo.verifyCarAtSpotOne(userId: _cleanUserId),
                        ),
                icon: const Icon(Icons.document_scanner_outlined),
                label: const Text('识别比对'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      if (_busy)
                        const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      else
                        const Icon(Icons.info_outline, size: 20),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _status,
                          style: theme.textTheme.titleMedium,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  if (_result.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    SelectableText(
                      _result,
                      style: theme.textTheme.bodySmall?.copyWith(
                        fontFamily: 'monospace',
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
