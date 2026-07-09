import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app/app.dart';
import 'app/app_settings.dart';
import 'app/session.dart';
import 'data/repository.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final settings = AppSettings();
  await settings.load();

  final session = AppSession();
  await session.load();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: settings),
        ChangeNotifierProvider.value(value: session),
        Provider<Repository>(
          create: (_) => TcpCarRepository(settings: settings),
        ),
      ],
      child: const App(),
    ),
  );
}
