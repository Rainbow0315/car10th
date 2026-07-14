import 'dart:convert';
import 'dart:io';

import 'package:car10th_mobile/app/app_settings.dart';
import 'package:car10th_mobile/data/repository.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('fleet velocity sends the same command to every selected TCP target',
      () async {
    final firstProbe = await _TcpProbe.start();
    final secondProbe = await _TcpProbe.start();
    final settings = _TestSettings([
      RobotControlTarget(
        code: 'robot_001',
        label: '小车1',
        host: InternetAddress.loopbackIPv4.address,
        tcpPort: firstProbe.port,
        apiBaseUrl: 'http://127.0.0.1:8000',
      ),
      RobotControlTarget(
        code: 'robot_002',
        label: '小车2',
        host: InternetAddress.loopbackIPv4.address,
        tcpPort: secondProbe.port,
        apiBaseUrl: 'http://127.0.0.1:8000',
      ),
    ]);
    final repository = TcpCarRepository(settings: settings);

    addTearDown(repository.dispose);
    addTearDown(firstProbe.close);
    addTearDown(secondProbe.close);

    await repository.sendFleetVelocity(
      robotCodes: ['robot_001', 'robot_002'],
      linearX: 0.2,
      linearY: 0.0,
      angularZ: 0.0,
    );

    await _waitFor(() {
      return firstProbe.messages.isNotEmpty && secondProbe.messages.isNotEmpty;
    });

    expect(firstProbe.messages.single, r'$011504011B#');
    expect(secondProbe.messages.single, r'$011504011B#');
  });
}

class _TestSettings extends AppSettings {
  final List<RobotControlTarget> _targets;

  _TestSettings(this._targets);

  @override
  List<RobotControlTarget> get controlTargets => _targets;

  @override
  String get controlRobotCode => _targets.first.code;

  @override
  RobotControlTarget get selectedControlTarget => _targets.first;

  @override
  String get tcpHost => _targets.first.host;

  @override
  int get tcpPort => _targets.first.tcpPort;
}

class _TcpProbe {
  final ServerSocket _server;
  final List<Socket> _clients = [];
  final List<String> messages = [];

  _TcpProbe._(this._server);

  int get port => _server.port;

  static Future<_TcpProbe> start() async {
    final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final probe = _TcpProbe._(server);
    server.listen((socket) {
      probe._clients.add(socket);
      socket.listen((data) {
        probe.messages.add(ascii.decode(data));
        socket.add(ascii.encode('OK\n'));
      });
    });
    return probe;
  }

  Future<void> close() async {
    for (final client in _clients) {
      client.destroy();
    }
    await _server.close();
  }
}

Future<void> _waitFor(bool Function() condition) async {
  final deadline = DateTime.now().add(const Duration(seconds: 2));
  while (DateTime.now().isBefore(deadline)) {
    if (condition()) return;
    await Future<void>.delayed(const Duration(milliseconds: 10));
  }
  fail('Condition was not met before timeout.');
}
