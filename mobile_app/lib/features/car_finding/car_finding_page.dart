import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/repository.dart';

class CarFindingPage extends StatefulWidget {
  const CarFindingPage({super.key});

  @override
  State<CarFindingPage> createState() => _CarFindingPageState();
}

class _CarFindingPageState extends State<CarFindingPage> {
  final _plate = TextEditingController();
  bool _busy = false;
  _PlateCheckResult? _result;
  String? _error;

  @override
  void dispose() {
    _plate.dispose();
    super.dispose();
  }

  Future<void> _startFinding() async {
    final plate = _plate.text.trim();
    if (_busy || plate.isEmpty) return;

    setState(() {
      _busy = true;
      _result = null;
      _error = null;
    });

    try {
      final json = await context.read<Repository>().verifyCarByPlate(
            plateNumber: plate,
          );
      if (!mounted) return;
      setState(() => _result = _PlateCheckResult.fromJson(json));
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = _friendlyError(error));
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  String _friendlyError(Object error) {
    final message = error.toString();
    if (message.contains('timed out') || message.contains('Timeout')) {
      return '摄像头取帧超时，请确认小车摄像头在线后重试。';
    }
    if (message.contains('failed_models') || message.contains('Internal Server Error')) {
      return '车牌识别服务暂时不可用，请确认服务已启动后重试。';
    }
    return '找车失败，请稍后重试。$message';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('引导找车')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _plate,
            textCapitalization: TextCapitalization.characters,
            onSubmitted: (_) => _startFinding(),
            decoration: const InputDecoration(
              labelText: '车牌号',
              prefixIcon: Icon(Icons.pin_outlined),
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 48,
            child: FilledButton.icon(
              onPressed: _busy ? null : _startFinding,
              icon: _busy
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.travel_explore),
              label: Text(_busy ? '正在识别' : '开始找车'),
            ),
          ),
          const SizedBox(height: 16),
          if (_error != null)
            _ResultCard(
              icon: Icons.error_outline,
              color: theme.colorScheme.error,
              title: '没有完成找车',
              lines: [_error!],
            )
          else if (_result != null)
            _ResultCard(
              icon: _result!.matched
                  ? Icons.check_circle_outline
                  : Icons.search_off_outlined,
              color: _result!.matched
                  ? Colors.green.shade700
                  : theme.colorScheme.primary,
              title: _result!.matched ? '找到目标车辆' : '暂未匹配到目标车牌',
              lines: _result!.displayLines,
            )
          else
            _ResultCard(
              icon: Icons.info_outline,
              color: theme.colorScheme.primary,
              title: '等待识别',
              lines: const ['输入车牌号后开始找车。'],
            ),
        ],
      ),
    );
  }
}

class _ResultCard extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String title;
  final List<String> lines;

  const _ResultCard({
    required this.icon,
    required this.color,
    required this.title,
    required this.lines,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    style: theme.textTheme.titleMedium,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            for (final line in lines)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text(line, style: theme.textTheme.bodyMedium),
              ),
          ],
        ),
      ),
    );
  }
}

class _PlateCheckResult {
  final bool matched;
  final String expectedPlate;
  final List<String> detectedPlates;
  final int totalDetections;
  final List<String> completedModels;
  final List<String> failedModels;

  const _PlateCheckResult({
    required this.matched,
    required this.expectedPlate,
    required this.detectedPlates,
    required this.totalDetections,
    required this.completedModels,
    required this.failedModels,
  });

  factory _PlateCheckResult.fromJson(Map<String, dynamic> json) {
    final detection = json['detection'];
    final summary = detection is Map ? detection['summary'] : null;
    final summaryMap = summary is Map ? summary : const {};
    return _PlateCheckResult(
      matched: json['matched'] == true,
      expectedPlate: (json['expected_plate'] ?? '-').toString(),
      detectedPlates: _stringList(json['detected_plates']),
      totalDetections: _asInt(summaryMap['total_detections']),
      completedModels: _stringList(summaryMap['completed_models']),
      failedModels: _stringList(summaryMap['failed_models']),
    );
  }

  List<String> get displayLines {
    final detected = detectedPlates.isEmpty ? '未识别到车牌' : detectedPlates.join('、');
    final lines = <String>[
      '目标车牌：$expectedPlate',
      '识别到的车牌：$detected',
      '比对结果：${matched ? '车牌一致，可以引导客户找车。' : '车牌不一致，请确认车牌或重新识别。'}',
    ];
    if (totalDetections > 0) {
      lines.add('识别到的目标数量：$totalDetections');
    }
    if (failedModels.isNotEmpty) {
      lines.add('识别状态：部分识别服务异常，建议重试。');
    } else if (completedModels.isNotEmpty) {
      lines.add('识别状态：识别完成。');
    }
    return lines;
  }

  static List<String> _stringList(Object? value) {
    if (value is! List) return const [];
    return value
        .map((item) => item.toString())
        .where((item) => item.trim().isNotEmpty)
        .toList(growable: false);
  }

  static int _asInt(Object? value) {
    if (value is int) return value;
    if (value is num) return value.round();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }
}
