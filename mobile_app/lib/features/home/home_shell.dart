import 'package:flutter/material.dart';

import '../alarm/alarm_list_page.dart';
import '../chat/chat_page.dart';
import '../dashboard/dashboard_page.dart';
import '../map/map_page.dart';
import '../settings/settings_page.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final pages = <Widget>[
      const DashboardPage(),
      const MapPage(),
      const ChatPage(),
      const AlarmListPage(),
      const SettingsPage(),
    ];

    return Scaffold(
      body: IndexedStack(
        index: _index,
        children: pages,
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (v) => setState(() => _index = v),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.dashboard_outlined), label: '总控'),
          NavigationDestination(icon: Icon(Icons.map_outlined), label: '地图'),
          NavigationDestination(
              icon: Icon(Icons.auto_awesome_outlined), label: '助手'),
          NavigationDestination(
              icon: Icon(Icons.notifications_none), label: '告警'),
          NavigationDestination(
              icon: Icon(Icons.settings_outlined), label: '设置'),
        ],
      ),
    );
  }
}
