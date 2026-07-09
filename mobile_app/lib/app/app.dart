import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../features/auth/login_page.dart';
import '../features/home/home_shell.dart';
import 'session.dart';

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) {
    final session = context.watch<AppSession>();

    return MaterialApp(
      title: '地下空间巡检',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1E5EFF)),
        useMaterial3: true,
      ),
      home: session.isLoggedIn ? const HomeShell() : const LoginPage(),
    );
  }
}

