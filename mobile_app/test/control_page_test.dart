import 'package:car10th_mobile/app/app_settings.dart';
import 'package:car10th_mobile/data/repository.dart';
import 'package:car10th_mobile/features/control/control_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

void main() {
  testWidgets('shows light effects and light show controls', (tester) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AppSettings()),
          Provider<Repository>(create: (_) => MockRepository()),
        ],
        child: const MaterialApp(home: ControlPage()),
      ),
    );

    expect(find.text('灯光控制'), findsOneWidget);
    expect(find.text('关闭'), findsOneWidget);
    expect(find.text('流水'), findsOneWidget);
    expect(find.text('跑马'), findsOneWidget);
    expect(find.text('呼吸'), findsOneWidget);
    expect(find.text('渐变'), findsOneWidget);
    expect(find.text('星光'), findsOneWidget);
    expect(find.text('开始灯光秀'), findsOneWidget);
    expect(find.text('停止灯光秀'), findsOneWidget);
    expect(find.text('播放音频'), findsOneWidget);

    await tester.tap(find.text('开始灯光秀'));
    await tester.pumpAndSettle();
    expect(find.text('启动灯光秀'), findsOneWidget);
  });
}
