import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../data/repository.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({super.key});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final _input = TextEditingController();
  final List<ChatMessage> _messages = [];
  bool _loading = false;
  String? _executingPlanId;
  LlmRuntimeStatus? _runtimeStatus;
  String? _runtimeStatusError;

  @override
  void initState() {
    super.initState();
    _loadRuntimeStatus();
  }

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  Future<void> _loadRuntimeStatus() async {
    try {
      final status = await context.read<Repository>().getLlmRuntimeStatus();
      if (!mounted) return;
      setState(() {
        _runtimeStatus = status;
        _runtimeStatusError = null;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _runtimeStatus = null;
        _runtimeStatusError = error.toString();
      });
    }
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    if (text.isEmpty || _loading) return;
    _input.clear();
    setState(() {
      _messages.add(
        ChatMessage(
          id: 'u_${DateTime.now().millisecondsSinceEpoch}',
          timestamp: DateTime.now(),
          isUser: true,
          text: text,
        ),
      );
      _loading = true;
    });

    try {
      final plan = await context.read<Repository>().planLlmTask(text);
      if (!mounted) return;
      setState(() {
        _messages.add(
          ChatMessage(
            id: 'a_${DateTime.now().millisecondsSinceEpoch}',
            timestamp: DateTime.now(),
            isUser: false,
            text: plan.assistantMessage,
            plan: plan,
          ),
        );
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _messages.add(
          ChatMessage(
            id: 'e_${DateTime.now().millisecondsSinceEpoch}',
            timestamp: DateTime.now(),
            isUser: false,
            text: '任务规划失败：$error',
          ),
        );
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _executePlan(LlmTaskPlan plan) async {
    if (_executingPlanId != null) return;
    setState(() => _executingPlanId = plan.planId);
    try {
      final result = await context.read<Repository>().executeLlmTask(
            planId: plan.planId,
            confirmed: true,
          );
      if (!mounted) return;
      setState(() {
        _messages.add(
          ChatMessage(
            id: 'x_${DateTime.now().millisecondsSinceEpoch}',
            timestamp: DateTime.now(),
            isUser: false,
            text: result.assistantMessage,
            plan: result,
          ),
        );
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _messages.add(
          ChatMessage(
            id: 'xerr_${DateTime.now().millisecondsSinceEpoch}',
            timestamp: DateTime.now(),
            isUser: false,
            text: '执行失败：$error',
          ),
        );
      });
    } finally {
      if (mounted) setState(() => _executingPlanId = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('智能任务助手'),
        actions: [
          IconButton(
            tooltip: '安全说明',
            onPressed: () => showDialog<void>(
              context: context,
              builder: (context) => AlertDialog(
                title: const Text('安全执行原则'),
                content: const Text(
                  '涉及运动的计划会先检查小车状态，并在执行前等待确认。',
                ),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('知道了'),
                  ),
                ],
              ),
            ),
            icon: const Icon(Icons.shield_outlined),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: _messages.length + 1,
              itemBuilder: (context, index) {
                if (index == 0) {
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Column(
                      children: [
                        _RuntimeStatusCard(
                          status: _runtimeStatus,
                          error: _runtimeStatusError,
                          onRefresh: _loadRuntimeStatus,
                        ),
                        const SizedBox(height: 10),
                        Card(
                          child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('你可以这样说',
                                    style: theme.textTheme.titleSmall),
                                const SizedBox(height: 8),
                                const Text('1) 查询 robot_001 现在是否在线'),
                                const Text('2) 急停 robot_001'),
                                const Text('3) 让 robot_001 核验 B2 消防通道的沪A12345'),
                                const SizedBox(height: 8),
                                Text(
                                  '涉及运动的计划会先展示给你确认，不会自动执行。',
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: theme.colorScheme.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  );
                }
                final m = _messages[index - 1];
                return _ChatBubble(
                  message: m,
                  executingPlanId: _executingPlanId,
                  onExecutePlan: _executePlan,
                );
              },
            ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _input,
                      decoration: const InputDecoration(
                        hintText: '输入问题…',
                        border: OutlineInputBorder(),
                      ),
                      minLines: 1,
                      maxLines: 4,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _send(),
                    ),
                  ),
                  const SizedBox(width: 10),
                  FilledButton(
                    onPressed: _loading ? null : _send,
                    child: _loading
                        ? const SizedBox(
                            height: 18,
                            width: 18,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.send),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _RuntimeStatusCard extends StatelessWidget {
  final LlmRuntimeStatus? status;
  final String? error;
  final VoidCallback onRefresh;

  const _RuntimeStatusCard({
    required this.status,
    required this.error,
    required this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final configured = status?.llmConfigured == true;
    final color = error != null
        ? theme.colorScheme.error
        : configured
            ? Colors.green
            : theme.colorScheme.secondary;
    final title = error != null
        ? 'LLM 状态读取失败'
        : configured
            ? '真实 LLM 已接入'
            : '当前使用规则兜底';
    final detail = error ?? (status == null ? '正在检查 LLM 配置…' : status!.message);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              configured ? Icons.cloud_done_outlined : Icons.rule_outlined,
              color: color,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: theme.textTheme.titleSmall),
                  const SizedBox(height: 4),
                  Text(
                    detail,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  if (status != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      '模式：${status!.plannerMode} · 模型：${status!.model}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            IconButton(
              tooltip: '刷新状态',
              onPressed: onRefresh,
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
      ),
    );
  }
}

class _ChatBubble extends StatelessWidget {
  final ChatMessage message;
  final String? executingPlanId;
  final ValueChanged<LlmTaskPlan> onExecutePlan;

  const _ChatBubble({
    required this.message,
    required this.executingPlanId,
    required this.onExecutePlan,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final align = message.isUser ? Alignment.centerRight : Alignment.centerLeft;
    final bg =
        message.isUser ? cs.primaryContainer : cs.surfaceContainerHighest;
    final fg = message.isUser ? cs.onPrimaryContainer : cs.onSurface;

    return Align(
      alignment: align,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: Card(
          color: bg,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  message.text,
                  style: theme.textTheme.bodyMedium?.copyWith(color: fg),
                ),
                if (message.plan != null) ...[
                  const SizedBox(height: 10),
                  _PlanCard(
                    plan: message.plan!,
                    executing: executingPlanId == message.plan!.planId,
                    onExecute: onExecutePlan,
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _PlanCard extends StatelessWidget {
  final LlmTaskPlan plan;
  final bool executing;
  final ValueChanged<LlmTaskPlan> onExecute;

  const _PlanCard({
    required this.plan,
    required this.executing,
    required this.onExecute,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final canExecute = plan.steps.any((step) => step.status == 'planned');

    return DecoratedBox(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  Icons.route_outlined,
                  size: 18,
                  color: theme.colorScheme.primary,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    '任务计划',
                    style: theme.textTheme.titleSmall,
                  ),
                ),
                Chip(
                  label: Text(plan.source),
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
            const SizedBox(height: 8),
            for (final step in plan.steps) _StepTile(step: step),
            if (plan.safetyNotes.isNotEmpty) ...[
              const SizedBox(height: 8),
              for (final note in plan.safetyNotes)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        Icons.verified_user_outlined,
                        size: 16,
                        color: theme.colorScheme.secondary,
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(note, style: theme.textTheme.bodySmall),
                      ),
                    ],
                  ),
                ),
            ],
            if (canExecute) ...[
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: executing ? null : () => onExecute(plan),
                  icon: executing
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.play_arrow),
                  label: Text(
                    plan.requiresConfirmation ? '确认并执行' : '执行计划',
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StepTile extends StatelessWidget {
  final LlmPlanStep step;

  const _StepTile({required this.step});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = switch (step.status) {
      'executed' => Colors.green,
      'failed' => theme.colorScheme.error,
      _ => theme.colorScheme.primary,
    };

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.circle, size: 10, color: color),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(step.title, style: theme.textTheme.bodyMedium),
                Text(
                  '${step.tool} · ${step.safetyLevel} · ${step.status}',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                if (step.arguments.isNotEmpty)
                  Text(
                    step.arguments.toString(),
                    style: theme.textTheme.bodySmall,
                  ),
                if (step.error != null)
                  Text(
                    step.error!,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.error,
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
