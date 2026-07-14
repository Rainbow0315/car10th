import 'package:car10th_mobile/app/app_settings.dart';
import 'package:car10th_mobile/data/repository.dart';
import 'package:car10th_mobile/features/inspection/camera_yolo_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

void main() {
  testWidgets('monitor card uses USB and can switch robot', (tester) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AppSettings()),
          Provider<Repository>(create: (_) => MockRepository()),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(child: CameraYoloCard()),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('监测监控'), findsOneWidget);
    expect(find.text('小车'), findsOneWidget);
    expect(find.text('小车2'), findsOneWidget);
    expect(find.text('USB'), findsOneWidget);

    await tester.tap(find.text('小车2'));
    await tester.pumpAndSettle();

    expect(find.text('小车1'), findsOneWidget);
    expect(find.text('Astra彩色'), findsNothing);
  });
}
