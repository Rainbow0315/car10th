import 'package:car10th_mobile/app/app_settings.dart';
import 'package:car10th_mobile/data/repository.dart';
import 'package:car10th_mobile/features/control/control_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

void main() {
  testWidgets('shows compact single-car console', (tester) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AppSettings()),
          Provider<Repository>(create: (_) => MockRepository()),
        ],
        child: const MaterialApp(home: ControlPage()),
      ),
    );

    expect(find.text('小车控制台'), findsOneWidget);
    expect(find.text('单车'), findsOneWidget);
    expect(find.text('多车'), findsOneWidget);
    expect(find.text('小车'), findsOneWidget);
    expect(find.text('方向'), findsOneWidget);
    expect(find.text('摇杆'), findsOneWidget);
    expect(find.text('前进'), findsOneWidget);
    expect(find.text('停车'), findsOneWidget);

    expect(find.text('拍照'), findsNothing);
    expect(find.text('开始录像'), findsNothing);
    expect(find.text('多车协同'), findsNothing);

    await tester.scrollUntilVisible(
      find.text('灯光控制'),
      300,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.pumpAndSettle();

    expect(find.text('灯光控制'), findsOneWidget);
    expect(find.text('关闭'), findsOneWidget);
    expect(find.text('流水'), findsOneWidget);
    expect(find.text('跑马'), findsOneWidget);
    expect(find.text('呼吸'), findsOneWidget);
    expect(find.text('渐变'), findsOneWidget);
    expect(find.text('星光'), findsOneWidget);
    expect(find.text('开始灯光秀'), findsOneWidget);
    expect(find.text('停止灯光秀'), findsOneWidget);

    await tester.scrollUntilVisible(
      find.text('音频控制'),
      300,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.pumpAndSettle();

    expect(find.text('音频控制'), findsOneWidget);
    expect(find.text('选择音频'), findsOneWidget);
    expect(find.text('前方有危险'), findsOneWidget);
    expect(find.text('播放音频'), findsOneWidget);
  });

  testWidgets('switches to fleet robot selection', (tester) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AppSettings()),
          Provider<Repository>(create: (_) => MockRepository()),
        ],
        child: const MaterialApp(home: ControlPage()),
      ),
    );

    await tester.tap(find.text('多车'));
    await tester.pumpAndSettle();

    expect(find.text('小车1'), findsOneWidget);
    expect(find.text('小车2'), findsOneWidget);
    expect(find.text('选中车辆前进 5s'), findsNothing);
    expect(find.textContaining('/api/'), findsNothing);
  });
}
