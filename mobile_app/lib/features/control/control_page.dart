import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app/app_settings.dart';
import '../../data/repository.dart';

class ControlPage extends StatefulWidget {
  const ControlPage({super.key});

  @override
  State<ControlPage> createState() => _ControlPageState();
}

class _ControlPageState extends State<ControlPage> {
  static const _repeatInterval = Duration(milliseconds: 120);

  double _speedScale = 0.65;
  double _leftFront = 0;
  double _leftRear = 0;
  double _rightFront = 0;
  double _rightRear = 0;
  bool _busy = false;
  String _lastCommand = '待机';
  Offset _stick = Offset.zero;
  Timer? _repeatTimer;
  Future<void> Function()? _repeatAction;
  bool _repeatSending = false;
  Offset? _latestVectorLocal;
  Size? _latestVectorSize;

  Repository get _repo => context.read<Repository>();

  Future<void> _send(
    String label,
    Future<void> Function(Repository repo) action, {
    bool toast = false,
    bool showBusy = true,
    bool showError = true,
  }) async {
    if (mounted) {
      setState(() {
        if (showBusy) _busy = true;
        _lastCommand = label;
      });
    }

    try {
      await action(_repo);
      if (!mounted || !toast) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$label 已发送'),
          duration: const Duration(milliseconds: 700),
        ),
      );
    } catch (e) {
      if (!mounted || !showError) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('TCP 控制失败：$e'),
          duration: const Duration(seconds: 4),
        ),
      );
    } finally {
      if (mounted && showBusy) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _stop({bool toast = false, bool showBusy = true}) {
    return _send(
      '停车',
      (repo) => repo.stopRobot(),
      toast: toast,
      showBusy: showBusy,
    );
  }

  void _startCommandRepeat(
    String label,
    Future<void> Function(Repository repo) action,
  ) {
    _startRepeating(
      () => _send(label, action, showBusy: false, showError: false),
    );
  }

  void _startRepeating(Future<void> Function() action) {
    _repeatTimer?.cancel();
    _repeatAction = action;
    unawaited(_runRepeatOnce());
    _repeatTimer = Timer.periodic(
      _repeatInterval,
      (_) => unawaited(_runRepeatOnce()),
    );
  }

  Future<void> _runRepeatOnce() async {
    if (_repeatSending) return;
    final action = _repeatAction;
    if (action == null) return;

    _repeatSending = true;
    try {
      await action();
    } finally {
      _repeatSending = false;
    }
  }

  Future<void> _stopRepeating() async {
    _repeatTimer?.cancel();
    _repeatTimer = null;
    _repeatAction = null;
    _latestVectorLocal = null;
    _latestVectorSize = null;
    await _stop();
    unawaited(
      Future<void>.delayed(const Duration(milliseconds: 160), () {
        if (!mounted || _repeatAction != null) return;
        unawaited(_stop(showBusy: false));
      }),
    );
  }

  _VectorMotion _vectorFrom(Offset local, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2;
    final raw = local - center;
    final clamped = raw.distance > radius
        ? Offset.fromDirection(raw.direction, radius)
        : raw;
    final x = (clamped.dx / radius) * _speedScale;
    final y = (-clamped.dy / radius) * _speedScale;
    return _VectorMotion(stick: clamped, x: x, y: y);
  }

  Future<void> _sendVector(Offset local, Size size) async {
    _latestVectorLocal = local;
    _latestVectorSize = size;
    final motion = _vectorFrom(local, size);
    setState(() {
      _stick = motion.stick;
      _lastCommand =
          '摇杆 x=${motion.x.toStringAsFixed(2)}, y=${motion.y.toStringAsFixed(2)}';
    });

    if (_repeatTimer == null) {
      _startRepeating(_sendLatestVector);
    }
  }

  Future<void> _sendLatestVector() async {
    final local = _latestVectorLocal;
    final size = _latestVectorSize;
    if (local == null || size == null) return;

    final motion = _vectorFrom(local, size);
    await _send(
      '摇杆 x=${motion.x.toStringAsFixed(2)}, y=${motion.y.toStringAsFixed(2)}',
      (repo) => repo.sendVectorMotion(x: motion.x, y: motion.y),
      showBusy: false,
      showError: false,
    );
  }

  Future<void> _releaseStick() async {
    setState(() => _stick = Offset.zero);
    await _stopRepeating();
  }

  Future<void> _sendWheelSpeeds() {
    return _send(
      '四轮速度',
      (repo) => repo.updateWheelSpeeds(
        leftFront: _leftFront,
        leftRear: _leftRear,
        rightFront: _rightFront,
        rightRear: _rightRear,
      ),
      toast: true,
    );
  }

  Future<void> _setLight(String label, RobotLightEffect effect) {
    return _send(label, (repo) => repo.setLightEffect(effect), toast: true);
  }

  @override
  void dispose() {
    _repeatTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final settings = context.watch<AppSettings>();

    return Scaffold(
      appBar: AppBar(title: const Text('TCP 小车控制台')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('连接', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 8),
                  const _KvRow(k: '协议', v: 'Yahboom TCP 私有协议'),
                  _KvRow(k: '地址', v: '${settings.tcpHost}:${settings.tcpPort}'),
                  _KvRow(k: '状态', v: _busy ? '发送中' : '空闲'),
                  _KvRow(k: '最后指令', v: _lastCommand),
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
                  Text('灯光控制', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _LightEffectButton(
                        label: '关闭',
                        icon: Icons.lightbulb_outline,
                        onPressed: () =>
                            _setLight('关闭灯光', RobotLightEffect.off),
                      ),
                      _LightEffectButton(
                        label: '流水',
                        icon: Icons.waves,
                        onPressed: () =>
                            _setLight('流水灯', RobotLightEffect.running),
                      ),
                      _LightEffectButton(
                        label: '跑马',
                        icon: Icons.animation,
                        onPressed: () =>
                            _setLight('跑马灯', RobotLightEffect.marquee),
                      ),
                      _LightEffectButton(
                        label: '呼吸',
                        icon: Icons.brightness_6_outlined,
                        onPressed: () =>
                            _setLight('呼吸灯', RobotLightEffect.breathing),
                      ),
                      _LightEffectButton(
                        label: '渐变',
                        icon: Icons.gradient,
                        onPressed: () =>
                            _setLight('渐变灯', RobotLightEffect.gradient),
                      ),
                      _LightEffectButton(
                        label: '星光',
                        icon: Icons.auto_awesome,
                        onPressed: () =>
                            _setLight('星光灯', RobotLightEffect.starlight),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: [
                      FilledButton.icon(
                        onPressed: () => _send(
                          '启动灯光秀',
                          (repo) => repo.startLightShow(),
                          toast: true,
                        ),
                        icon: const Icon(Icons.music_note),
                        label: const Text('开始灯光秀'),
                      ),
                      OutlinedButton.icon(
                        onPressed: () => _send(
                          '停止灯光秀',
                          (repo) => repo.stopLightShow(),
                          toast: true,
                        ),
                        icon: const Icon(Icons.stop_circle_outlined),
                        label: const Text('停止灯光秀'),
                      ),
                      FilledButton.tonalIcon(
                        onPressed: () => _send(
                          '播放音频',
                          (repo) => repo.playAudio(),
                          toast: true,
                        ),
                        icon: const Icon(Icons.volume_up_outlined),
                        label: const Text('播放音频'),
                      ),
                    ],
                  ),
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
                  Text('方向控制', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 12),
                  Center(
                    child: SizedBox(
                      width: 276,
                      child: GridView.count(
                        crossAxisCount: 3,
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        mainAxisSpacing: 10,
                        crossAxisSpacing: 10,
                        children: [
                          _HoldCommandButton(
                            icon: Icons.rotate_left,
                            label: '左转',
                            onDown: () => _startCommandRepeat(
                              '左转',
                              (repo) => repo.rotateLeft(),
                            ),
                            onUp: () => unawaited(_stopRepeating()),
                          ),
                          _HoldCommandButton(
                            icon: Icons.keyboard_arrow_up,
                            label: '前进',
                            onDown: () => _startCommandRepeat(
                              '前进',
                              (repo) => repo.sendForward(speedMps: _speedScale),
                            ),
                            onUp: () => unawaited(_stopRepeating()),
                          ),
                          _HoldCommandButton(
                            icon: Icons.rotate_right,
                            label: '右转',
                            onDown: () => _startCommandRepeat(
                              '右转',
                              (repo) => repo.rotateRight(),
                            ),
                            onUp: () => unawaited(_stopRepeating()),
                          ),
                          _HoldCommandButton(
                            icon: Icons.keyboard_arrow_left,
                            label: '左移',
                            onDown: () => _startCommandRepeat(
                              '左移',
                              (repo) => repo.sendLeft(),
                            ),
                            onUp: () => unawaited(_stopRepeating()),
                          ),
                          _TapCommandButton(
                            icon: Icons.stop,
                            label: '停车',
                            onTap: () => _stop(toast: true),
                          ),
                          _HoldCommandButton(
                            icon: Icons.keyboard_arrow_right,
                            label: '右移',
                            onDown: () => _startCommandRepeat(
                              '右移',
                              (repo) => repo.sendRight(),
                            ),
                            onUp: () => unawaited(_stopRepeating()),
                          ),
                          const SizedBox.shrink(),
                          _HoldCommandButton(
                            icon: Icons.keyboard_arrow_down,
                            label: '后退',
                            onDown: () => _startCommandRepeat(
                              '后退',
                              (repo) => repo.sendBackward(),
                            ),
                            onUp: () => unawaited(_stopRepeating()),
                          ),
                          _TapCommandButton(
                            icon: Icons.do_not_disturb_on,
                            label: '刹停',
                            onTap: () => _send(
                              '刹停',
                              (repo) => repo.brakeRobot(),
                              toast: true,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
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
                  Text('摇杆控制', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 12),
                  Center(
                    child: _JoystickPad(
                      stick: _stick,
                      onMove: _sendVector,
                      onRelease: _releaseStick,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '速度比例：${(_speedScale * 100).round()}%',
                    style: theme.textTheme.bodySmall,
                  ),
                  Slider(
                    value: _speedScale,
                    min: 0.2,
                    max: 1.0,
                    divisions: 8,
                    label: '${(_speedScale * 100).round()}%',
                    onChanged: (v) => setState(() => _speedScale = v),
                  ),
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
                  Text('快捷功能', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: [
                      FilledButton.tonalIcon(
                        onPressed: () => _send(
                          '拍照',
                          (repo) => repo.takePhoto(),
                          toast: true,
                        ),
                        icon: const Icon(Icons.photo_camera_outlined),
                        label: const Text('拍照'),
                      ),
                      FilledButton.tonalIcon(
                        onPressed: () => _send(
                          '开始录像',
                          (repo) => repo.startRecording(),
                          toast: true,
                        ),
                        icon: const Icon(Icons.videocam_outlined),
                        label: const Text('开始录像'),
                      ),
                      FilledButton.tonalIcon(
                        onPressed: () => _send(
                          '结束录像',
                          (repo) => repo.stopRecording(),
                          toast: true,
                        ),
                        icon: const Icon(Icons.videocam_off_outlined),
                        label: const Text('结束录像'),
                      ),
                      FilledButton.tonalIcon(
                        onPressed: () => _send(
                          '启动巡航',
                          (repo) => repo.startTracking(),
                          toast: true,
                        ),
                        icon: const Icon(Icons.route_outlined),
                        label: const Text('启动巡航'),
                      ),
                      FilledButton.tonalIcon(
                        onPressed: () => _send(
                          '停止巡航',
                          (repo) => repo.stopTracking(),
                          toast: true,
                        ),
                        icon: const Icon(Icons.pause_circle_outline),
                        label: const Text('停止巡航'),
                      ),
                    ],
                  ),
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
                  Text('四轮单独速度', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 8),
                  _WheelSlider(
                    label: '左前轮',
                    value: _leftFront,
                    onChanged: (v) => setState(() => _leftFront = v),
                  ),
                  _WheelSlider(
                    label: '左后轮',
                    value: _leftRear,
                    onChanged: (v) => setState(() => _leftRear = v),
                  ),
                  _WheelSlider(
                    label: '右前轮',
                    value: _rightFront,
                    onChanged: (v) => setState(() => _rightFront = v),
                  ),
                  _WheelSlider(
                    label: '右后轮',
                    value: _rightRear,
                    onChanged: (v) => setState(() => _rightRear = v),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      FilledButton.tonalIcon(
                        onPressed: _sendWheelSpeeds,
                        icon: const Icon(Icons.speed),
                        label: const Text('发送四轮速度'),
                      ),
                      const SizedBox(width: 10),
                      OutlinedButton.icon(
                        onPressed: () {
                          setState(() {
                            _leftFront = 0;
                            _leftRear = 0;
                            _rightFront = 0;
                            _rightRear = 0;
                          });
                          unawaited(_stop(toast: true));
                        },
                        icon: const Icon(Icons.refresh),
                        label: const Text('清零'),
                      ),
                    ],
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

class _HoldCommandButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onDown;
  final VoidCallback onUp;

  const _HoldCommandButton({
    required this.icon,
    required this.label,
    required this.onDown,
    required this.onUp,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTapDown: (_) => onDown(),
      onTapUp: (_) => onUp(),
      onTapCancel: onUp,
      child: _CommandSurface(icon: icon, label: label, filled: false),
    );
  }
}

class _VectorMotion {
  final Offset stick;
  final double x;
  final double y;

  const _VectorMotion({required this.stick, required this.x, required this.y});
}

class _TapCommandButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _TapCommandButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(8),
      onTap: onTap,
      child: _CommandSurface(icon: icon, label: label, filled: true),
    );
  }
}

class _LightEffectButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onPressed;

  const _LightEffectButton({
    required this.label,
    required this.icon,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 104,
      height: 44,
      child: FilledButton.tonalIcon(
        onPressed: onPressed,
        icon: Icon(icon, size: 19),
        label: Text(label),
      ),
    );
  }
}

class _CommandSurface extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool filled;

  const _CommandSurface({
    required this.icon,
    required this.label,
    required this.filled,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color:
            filled ? colors.primaryContainer : colors.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 28),
          const SizedBox(height: 4),
          Text(label, style: theme.textTheme.labelMedium),
        ],
      ),
    );
  }
}

class _JoystickPad extends StatelessWidget {
  final Offset stick;
  final Future<void> Function(Offset local, Size size) onMove;
  final Future<void> Function() onRelease;

  const _JoystickPad({
    required this.stick,
    required this.onMove,
    required this.onRelease,
  });

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return LayoutBuilder(
      builder: (context, constraints) {
        const size = 220.0;
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onPanDown: (details) =>
              unawaited(onMove(details.localPosition, const Size(size, size))),
          onPanUpdate: (details) =>
              unawaited(onMove(details.localPosition, const Size(size, size))),
          onPanEnd: (_) => unawaited(onRelease()),
          onPanCancel: () => unawaited(onRelease()),
          child: SizedBox.square(
            dimension: size,
            child: DecoratedBox(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: colors.surfaceContainerHighest,
                border: Border.all(color: colors.outlineVariant),
              ),
              child: Stack(
                alignment: Alignment.center,
                children: [
                  Container(
                    width: 2,
                    height: 170,
                    color: colors.outlineVariant,
                  ),
                  Container(
                    width: 170,
                    height: 2,
                    color: colors.outlineVariant,
                  ),
                  Transform.translate(
                    offset: stick,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: colors.primary,
                      ),
                      child: const SizedBox.square(
                        dimension: 62,
                        child: Icon(Icons.gamepad_outlined),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _WheelSlider extends StatelessWidget {
  final String label;
  final double value;
  final ValueChanged<double> onChanged;

  const _WheelSlider({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        SizedBox(width: 64, child: Text(label)),
        Expanded(
          child: Slider(
            value: value,
            min: -1,
            max: 1,
            divisions: 20,
            label: '${(value * 100).round()}',
            onChanged: onChanged,
          ),
        ),
        SizedBox(
          width: 42,
          child: Text('${(value * 100).round()}', textAlign: TextAlign.end),
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
