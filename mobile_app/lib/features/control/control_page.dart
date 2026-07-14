import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app/app_settings.dart';
import '../../data/repository.dart';

enum _ControlMode { single, fleet }

enum _ControlSurface { direction, joystick }

class ControlPage extends StatefulWidget {
  const ControlPage({super.key});

  @override
  State<ControlPage> createState() => _ControlPageState();
}

class _ControlPageState extends State<ControlPage> {
  static const _repeatInterval = Duration(milliseconds: 120);
  static const _baseLinearSpeed = 0.18;
  static const _baseAngularSpeed = 0.9;
  static const _commandDuration = 0.35;

  _ControlMode _mode = _ControlMode.single;
  _ControlSurface _surface = _ControlSurface.direction;
  final Set<String> _selectedRobots = {'robot_001'};
  double _speedScale = 0.65;
  bool _busy = false;
  bool _autoFollowOn = false;
  String _lastCommand = '待机';
  Offset _stick = Offset.zero;
  Timer? _repeatTimer;
  Future<void> Function()? _repeatAction;
  bool _repeatSending = false;
  Offset? _latestVectorLocal;
  Size? _latestVectorSize;
  RobotLightEffect _selectedLightEffect = RobotLightEffect.off;
  RobotAudioClip _selectedAudioClip = RobotAudioClip.warning;
  double _audioVolume = 80;

  Repository get _repo => context.read<Repository>();

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final code = context.read<AppSettings>().controlRobotCode;
    if (_mode == _ControlMode.single && !_selectedRobots.contains(code)) {
      _selectedRobots
        ..clear()
        ..add(code);
    }
  }

  List<String> get _robotCodes {
    final list = _selectedRobots.toList()..sort();
    return list;
  }

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
          content: Text('控制失败：$e'),
          duration: const Duration(seconds: 4),
        ),
      );
    } finally {
      if (mounted && showBusy) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _sendVelocity(
    String label, {
    required double linearX,
    required double linearY,
    required double angularZ,
    bool showBusy = false,
    bool showError = false,
  }) {
    if (_mode == _ControlMode.fleet) {
      return _send(
        label,
        (repo) => repo.sendFleetVelocity(
          robotCodes: _robotCodes,
          linearX: linearX,
          linearY: linearY,
          angularZ: angularZ,
          durationSeconds: _commandDuration,
        ),
        showBusy: showBusy,
        showError: showError,
      );
    }

    Future<void> Function(Repository repo) action;
    if (linearX > 0) {
      action = (repo) => repo.sendForward(speedMps: linearX);
    } else if (linearX < 0) {
      action = (repo) => repo.sendBackward();
    } else if (linearY > 0) {
      action = (repo) => repo.sendLeft();
    } else if (linearY < 0) {
      action = (repo) => repo.sendRight();
    } else if (angularZ > 0) {
      action = (repo) => repo.rotateLeft();
    } else if (angularZ < 0) {
      action = (repo) => repo.rotateRight();
    } else {
      action = (repo) => repo.stopRobot();
    }
    return _send(
      label,
      action,
      showBusy: showBusy,
      showError: showError,
    );
  }

  Future<void> _stop({bool toast = false, bool showBusy = true}) {
    if (_mode == _ControlMode.fleet) {
      return _send(
        '停车',
        (repo) => repo.stopFleetRobots(robotCodes: _robotCodes),
        toast: toast,
        showBusy: showBusy,
      );
    }
    return _send(
      '停车',
      (repo) => repo.stopRobot(),
      toast: toast,
      showBusy: showBusy,
    );
  }

  Future<void> _setAutoFollow(bool enabled) async {
    final isFleet = _mode == _ControlMode.fleet;

    await _send(
      enabled ? '自动跟随' : '停止跟随',
      (repo) {
        if (isFleet) {
          return enabled
              ? repo.startFleetTracking(robotCodes: _robotCodes)
              : repo.stopFleetTracking(robotCodes: _robotCodes);
        }
        return enabled ? repo.startTracking() : repo.stopTracking();
      },
      toast: true,
    );
    if (!mounted) return;
    setState(() => _autoFollowOn = enabled);
  }

  Future<void> _stopAutoFollow({bool showBusy = true}) async {
    if (!_autoFollowOn) return;
    final isFleet = _mode == _ControlMode.fleet;

    await _send(
      '停止跟随',
      (repo) => isFleet
          ? repo.stopFleetTracking(robotCodes: _robotCodes)
          : repo.stopTracking(),
      showBusy: showBusy,
      showError: false,
    );
    if (!mounted) return;
    setState(() => _autoFollowOn = false);
  }

  void _startRepeating(Future<void> Function() action) {
    if (_autoFollowOn) {
      unawaited(_stopAutoFollow(showBusy: false));
    }
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
    await _stop(showBusy: false);
    unawaited(
      Future<void>.delayed(const Duration(milliseconds: 160), () {
        if (!mounted || _repeatAction != null) return;
        unawaited(_stop(showBusy: false));
      }),
    );
  }

  Future<void> _selectSingleRobot(String robotCode) async {
    final settings = context.read<AppSettings>();
    await _stopAutoFollow(showBusy: false);
    await settings.selectControlRobot(robotCode);
    if (!mounted) return;
    setState(() {
      _selectedRobots
        ..clear()
        ..add(robotCode);
      _lastCommand = '已选择 $robotCode';
    });
  }

  void _toggleFleetRobot(String robotCode, bool selected) {
    setState(() {
      if (selected) {
        _selectedRobots.add(robotCode);
      } else if (_selectedRobots.length > 1) {
        _selectedRobots.remove(robotCode);
      }
    });
  }

  Future<void> _setMode(_ControlMode mode) async {
    if (_mode == mode) return;
    await _stopAutoFollow(showBusy: false);
    await _stop(showBusy: false);
    if (!mounted) return;
    final settings = context.read<AppSettings>();
    setState(() {
      _mode = mode;
      _selectedRobots.clear();
      if (mode == _ControlMode.single) {
        _selectedRobots.add(settings.selectedControlTarget.code);
      } else {
        _selectedRobots.addAll(
          settings.controlTargets.map((target) => target.code),
        );
      }
      _stick = Offset.zero;
      _lastCommand = mode == _ControlMode.single ? '单车模式' : '多车模式';
    });
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
    if (_mode == _ControlMode.single) {
      await _send(
        '摇杆 x=${motion.x.toStringAsFixed(2)}, y=${motion.y.toStringAsFixed(2)}',
        (repo) => repo.sendVectorMotion(x: motion.x, y: motion.y),
        showBusy: false,
        showError: false,
      );
      return;
    }

    await _sendFleetVector(motion);
  }

  Future<void> _sendFleetVector(_VectorMotion motion) {
    return _send(
      '摇杆 x=${motion.x.toStringAsFixed(2)}, y=${motion.y.toStringAsFixed(2)}',
      (repo) => repo.sendFleetVectorMotion(
        robotCodes: _robotCodes,
        x: motion.x,
        y: motion.y,
      ),
      showBusy: false,
      showError: false,
    );
  }

  Future<void> _releaseStick() async {
    setState(() => _stick = Offset.zero);
    await _stopRepeating();
  }

  void _showSpeedSheet() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) {
        var draft = _speedScale;
        return StatefulBuilder(
          builder: (context, setSheetState) {
            return Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('速度', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      const Icon(Icons.speed),
                      Expanded(
                        child: Slider(
                          value: draft,
                          min: 0.2,
                          max: 1.0,
                          divisions: 8,
                          label: '${(draft * 100).round()}%',
                          onChanged: (value) {
                            setSheetState(() => draft = value);
                            setState(() => _speedScale = value);
                          },
                        ),
                      ),
                      SizedBox(
                        width: 48,
                        child: Text(
                          '${(draft * 100).round()}%',
                          textAlign: TextAlign.end,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            );
          },
        );
      },
    );
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
    final currentCode = settings.controlTargets.any(
      (target) => target.code == settings.controlRobotCode,
    )
        ? settings.controlRobotCode
        : settings.selectedControlTarget.code;

    if (_mode == _ControlMode.single &&
        !_selectedRobots.contains(currentCode)) {
      _selectedRobots
        ..clear()
        ..add(currentCode);
    }

    return Scaffold(
      appBar: AppBar(title: const Text('小车控制台')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    SegmentedButton<_ControlMode>(
                      segments: const [
                        ButtonSegment(
                          value: _ControlMode.single,
                          label: Text('单车'),
                          icon: Icon(Icons.directions_car_outlined),
                        ),
                        ButtonSegment(
                          value: _ControlMode.fleet,
                          label: Text('多车'),
                          icon: Icon(Icons.groups_2_outlined),
                        ),
                      ],
                      selected: {_mode},
                      onSelectionChanged: _busy || _repeatTimer != null
                          ? null
                          : (values) => unawaited(_setMode(values.first)),
                    ),
                    SegmentedButton<_ControlSurface>(
                      segments: const [
                        ButtonSegment(
                          value: _ControlSurface.direction,
                          label: Text('方向'),
                          icon: Icon(Icons.open_with),
                        ),
                        ButtonSegment(
                          value: _ControlSurface.joystick,
                          label: Text('摇杆'),
                          icon: Icon(Icons.gamepad_outlined),
                        ),
                      ],
                      selected: {_surface},
                      onSelectionChanged: _repeatTimer != null
                          ? null
                          : (values) => setState(() => _surface = values.first),
                    ),
                    IconButton.filledTonal(
                      tooltip: '速度',
                      onPressed: _showSpeedSheet,
                      icon: const Icon(Icons.tune),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                if (_mode == _ControlMode.single)
                  DropdownButtonFormField<String>(
                    initialValue: currentCode,
                    decoration: const InputDecoration(
                      labelText: '小车',
                      prefixIcon: Icon(Icons.directions_car_filled_outlined),
                    ),
                    items: [
                      for (final target in settings.controlTargets)
                        DropdownMenuItem(
                          value: target.code,
                          child: Text(target.label),
                        ),
                    ],
                    onChanged: _busy || _repeatTimer != null
                        ? null
                        : (value) {
                            if (value != null) {
                              unawaited(_selectSingleRobot(value));
                            }
                          },
                  )
                else
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final target in settings.controlTargets)
                        FilterChip(
                          selected: _selectedRobots.contains(target.code),
                          label: Text(target.label),
                          avatar: const Icon(Icons.directions_car_outlined),
                          onSelected: _busy || _repeatTimer != null
                              ? null
                              : (selected) =>
                                  _toggleFleetRobot(target.code, selected),
                        ),
                    ],
                  ),
                const SizedBox(height: 8),
                Text(
                  '${_busy ? '发送中' : '空闲'} · $_lastCommand',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: _surface == _ControlSurface.direction
                ? _DirectionTab(
                    speedScale: _speedScale,
                    autoFollowOn: _autoFollowOn,
                    autoFollowEnabled: _repeatTimer == null &&
                        (_mode == _ControlMode.single ||
                            _robotCodes.isNotEmpty),
                    onCommandDown: _startDirection,
                    onCommandUp: () => unawaited(_stopRepeating()),
                    onStop: () async {
                      await _stopAutoFollow(showBusy: false);
                      await _stop(toast: true);
                    },
                    onBrake: () => _send(
                      '刹停',
                      (repo) => _mode == _ControlMode.fleet
                          ? repo.stopFleetRobots(robotCodes: _robotCodes)
                          : repo.brakeRobot(),
                      toast: true,
                    ),
                    onToggleAutoFollow: _setAutoFollow,
                    selectedLightEffect: _selectedLightEffect,
                    onSetLightEffect: (effect) {
                      setState(() => _selectedLightEffect = effect);
                      return _send(
                        _lightEffectLabel(effect),
                        (repo) => repo.setLightEffect(effect),
                        toast: true,
                      );
                    },
                    onStartLightShow: () => _send(
                      '开始灯光秀',
                      (repo) => repo.startLightShow(),
                      toast: true,
                    ),
                    onStopLightShow: () => _send(
                      '停止灯光秀',
                      (repo) => repo.stopLightShow(),
                      toast: true,
                    ),
                    selectedAudioClip: _selectedAudioClip,
                    audioVolume: _audioVolume,
                    onAudioClipChanged: (clip) {
                      setState(() => _selectedAudioClip = clip);
                    },
                    onAudioVolumeChanged: (value) {
                      setState(() => _audioVolume = value);
                    },
                    onPlayAudio: () => _send(
                      '播放音频',
                      (repo) => repo.playAudio(
                        clip: _selectedAudioClip,
                        volumePercent: _audioVolume.round(),
                      ),
                      toast: true,
                    ),
                  )
                : _JoystickTab(
                    speedScale: _speedScale,
                    stick: _stick,
                    onMove: _sendVector,
                    onRelease: _releaseStick,
                    onStop: () async {
                      await _stopAutoFollow(showBusy: false);
                      await _stop(toast: true);
                    },
                  ),
          ),
        ],
      ),
    );
  }

  void _startDirection(_MotionPreset preset) {
    final linear = _baseLinearSpeed * _speedScale;
    final angular = _baseAngularSpeed * _speedScale;
    _startRepeating(() {
      switch (preset) {
        case _MotionPreset.forward:
          return _sendVelocity(
            '前进',
            linearX: linear,
            linearY: 0.0,
            angularZ: 0.0,
          );
        case _MotionPreset.backward:
          return _sendVelocity(
            '后退',
            linearX: -linear,
            linearY: 0.0,
            angularZ: 0.0,
          );
        case _MotionPreset.left:
          return _sendVelocity(
            '左移',
            linearX: 0.0,
            linearY: linear,
            angularZ: 0.0,
          );
        case _MotionPreset.right:
          return _sendVelocity(
            '右移',
            linearX: 0.0,
            linearY: -linear,
            angularZ: 0.0,
          );
        case _MotionPreset.rotateLeft:
          return _sendVelocity(
            '左转',
            linearX: 0.0,
            linearY: 0.0,
            angularZ: angular,
          );
        case _MotionPreset.rotateRight:
          return _sendVelocity(
            '右转',
            linearX: 0.0,
            linearY: 0.0,
            angularZ: -angular,
          );
      }
    });
  }
}

enum _MotionPreset {
  forward,
  backward,
  left,
  right,
  rotateLeft,
  rotateRight,
}

class _DirectionTab extends StatelessWidget {
  final double speedScale;
  final bool autoFollowOn;
  final bool autoFollowEnabled;
  final ValueChanged<_MotionPreset> onCommandDown;
  final VoidCallback onCommandUp;
  final Future<void> Function() onStop;
  final Future<void> Function() onBrake;
  final Future<void> Function(bool enabled) onToggleAutoFollow;
  final RobotLightEffect selectedLightEffect;
  final Future<void> Function(RobotLightEffect effect) onSetLightEffect;
  final Future<void> Function() onStartLightShow;
  final Future<void> Function() onStopLightShow;
  final RobotAudioClip selectedAudioClip;
  final double audioVolume;
  final ValueChanged<RobotAudioClip> onAudioClipChanged;
  final ValueChanged<double> onAudioVolumeChanged;
  final Future<void> Function() onPlayAudio;

  const _DirectionTab({
    required this.speedScale,
    required this.autoFollowOn,
    required this.autoFollowEnabled,
    required this.onCommandDown,
    required this.onCommandUp,
    required this.onStop,
    required this.onBrake,
    required this.onToggleAutoFollow,
    required this.selectedLightEffect,
    required this.onSetLightEffect,
    required this.onStartLightShow,
    required this.onStopLightShow,
    required this.selectedAudioClip,
    required this.audioVolume,
    required this.onAudioClipChanged,
    required this.onAudioVolumeChanged,
    required this.onPlayAudio,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          children: [
            Text('速度 ${(speedScale * 100).round()}%'),
            const Spacer(),
            Text(
              '长按发送',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Align(
          alignment: Alignment.centerLeft,
          child: FilledButton.icon(
            onPressed: autoFollowEnabled
                ? () => unawaited(onToggleAutoFollow(!autoFollowOn))
                : null,
            icon: Icon(
              autoFollowOn
                  ? Icons.person_off_outlined
                  : Icons.transfer_within_a_station_outlined,
            ),
            label: Text(autoFollowOn ? '停止跟随' : '自动跟随'),
          ),
        ),
        const SizedBox(height: 14),
        Center(
          child: SizedBox(
            width: 284,
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
                  onDown: () => onCommandDown(_MotionPreset.rotateLeft),
                  onUp: onCommandUp,
                ),
                _HoldCommandButton(
                  icon: Icons.keyboard_arrow_up,
                  label: '前进',
                  onDown: () => onCommandDown(_MotionPreset.forward),
                  onUp: onCommandUp,
                ),
                _HoldCommandButton(
                  icon: Icons.rotate_right,
                  label: '右转',
                  onDown: () => onCommandDown(_MotionPreset.rotateRight),
                  onUp: onCommandUp,
                ),
                _HoldCommandButton(
                  icon: Icons.keyboard_arrow_left,
                  label: '左移',
                  onDown: () => onCommandDown(_MotionPreset.left),
                  onUp: onCommandUp,
                ),
                _TapCommandButton(
                  icon: Icons.stop,
                  label: '停车',
                  onTap: () => unawaited(onStop()),
                ),
                _HoldCommandButton(
                  icon: Icons.keyboard_arrow_right,
                  label: '右移',
                  onDown: () => onCommandDown(_MotionPreset.right),
                  onUp: onCommandUp,
                ),
                const SizedBox.shrink(),
                _HoldCommandButton(
                  icon: Icons.keyboard_arrow_down,
                  label: '后退',
                  onDown: () => onCommandDown(_MotionPreset.backward),
                  onUp: onCommandUp,
                ),
                _TapCommandButton(
                  icon: Icons.do_not_disturb_on,
                  label: '刹停',
                  onTap: () => unawaited(onBrake()),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 18),
        _LightControlPanel(
          selectedEffect: selectedLightEffect,
          onSetEffect: onSetLightEffect,
          onStartLightShow: onStartLightShow,
          onStopLightShow: onStopLightShow,
        ),
        const SizedBox(height: 16),
        _AudioControlPanel(
          selectedClip: selectedAudioClip,
          volume: audioVolume,
          onClipChanged: onAudioClipChanged,
          onVolumeChanged: onAudioVolumeChanged,
          onPlayAudio: onPlayAudio,
        ),
      ],
    );
  }
}

class _LightControlPanel extends StatelessWidget {
  final RobotLightEffect selectedEffect;
  final Future<void> Function(RobotLightEffect effect) onSetEffect;
  final Future<void> Function() onStartLightShow;
  final Future<void> Function() onStopLightShow;

  const _LightControlPanel({
    required this.selectedEffect,
    required this.onSetEffect,
    required this.onStartLightShow,
    required this.onStopLightShow,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('灯光控制', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final effect in RobotLightEffect.values)
              ChoiceChip(
                avatar: Icon(_lightEffectIcon(effect), size: 18),
                label: Text(_lightEffectLabel(effect)),
                selected: selectedEffect == effect,
                onSelected: (_) => unawaited(onSetEffect(effect)),
              ),
          ],
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            FilledButton.tonalIcon(
              onPressed: () => unawaited(onStartLightShow()),
              icon: const Icon(Icons.auto_awesome),
              label: const Text('开始灯光秀'),
            ),
            OutlinedButton.icon(
              onPressed: () => unawaited(onStopLightShow()),
              icon: const Icon(Icons.lightbulb_outline),
              label: const Text('停止灯光秀'),
            ),
          ],
        ),
      ],
    );
  }
}

class _AudioControlPanel extends StatelessWidget {
  final RobotAudioClip selectedClip;
  final double volume;
  final ValueChanged<RobotAudioClip> onClipChanged;
  final ValueChanged<double> onVolumeChanged;
  final Future<void> Function() onPlayAudio;

  const _AudioControlPanel({
    required this.selectedClip,
    required this.volume,
    required this.onClipChanged,
    required this.onVolumeChanged,
    required this.onPlayAudio,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('音频控制', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 10),
        DropdownButtonFormField<RobotAudioClip>(
          initialValue: selectedClip,
          decoration: const InputDecoration(
            labelText: '选择音频',
            prefixIcon: Icon(Icons.library_music_outlined),
          ),
          items: [
            for (final clip in RobotAudioClip.values)
              DropdownMenuItem(
                value: clip,
                child: Text(_audioClipLabel(clip)),
              ),
          ],
          onChanged: (value) {
            if (value != null) onClipChanged(value);
          },
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            const Icon(Icons.volume_up_outlined),
            Expanded(
              child: Slider(
                value: volume,
                min: 0,
                max: 100,
                divisions: 10,
                label: '${volume.round()}%',
                onChanged: onVolumeChanged,
              ),
            ),
            SizedBox(
              width: 44,
              child: Text(
                '${volume.round()}%',
                textAlign: TextAlign.end,
              ),
            ),
          ],
        ),
        FilledButton.icon(
          onPressed: () => unawaited(onPlayAudio()),
          icon: const Icon(Icons.volume_up_outlined),
          label: const Text('播放音频'),
        ),
      ],
    );
  }
}

class _JoystickTab extends StatelessWidget {
  final double speedScale;
  final Offset stick;
  final Future<void> Function(Offset local, Size size) onMove;
  final Future<void> Function() onRelease;
  final Future<void> Function() onStop;

  const _JoystickTab({
    required this.speedScale,
    required this.stick,
    required this.onMove,
    required this.onRelease,
    required this.onStop,
  });

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          children: [
            Text('速度 ${(speedScale * 100).round()}%'),
            const Spacer(),
            IconButton.filledTonal(
              tooltip: '停车',
              onPressed: () => unawaited(onStop()),
              icon: const Icon(Icons.stop),
            ),
          ],
        ),
        const SizedBox(height: 18),
        Center(
          child: _JoystickPad(
            stick: stick,
            onMove: onMove,
            onRelease: onRelease,
          ),
        ),
      ],
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
              Container(width: 2, height: 170, color: colors.outlineVariant),
              Container(width: 170, height: 2, color: colors.outlineVariant),
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
  }
}

String _lightEffectLabel(RobotLightEffect effect) {
  return switch (effect) {
    RobotLightEffect.off => '关闭',
    RobotLightEffect.running => '流水',
    RobotLightEffect.marquee => '跑马',
    RobotLightEffect.breathing => '呼吸',
    RobotLightEffect.gradient => '渐变',
    RobotLightEffect.starlight => '星光',
  };
}

IconData _lightEffectIcon(RobotLightEffect effect) {
  return switch (effect) {
    RobotLightEffect.off => Icons.lightbulb_outline,
    RobotLightEffect.running => Icons.waves,
    RobotLightEffect.marquee => Icons.directions_run,
    RobotLightEffect.breathing => Icons.air,
    RobotLightEffect.gradient => Icons.gradient,
    RobotLightEffect.starlight => Icons.auto_awesome,
  };
}

String _audioClipLabel(RobotAudioClip clip) {
  return switch (clip) {
    RobotAudioClip.warning => '前方有危险',
    RobotAudioClip.lightShow => '灯光秀',
    RobotAudioClip.systemPrompt => '系统提示',
  };
}

class _VectorMotion {
  final Offset stick;
  final double x;
  final double y;

  const _VectorMotion({required this.stick, required this.x, required this.y});
}
