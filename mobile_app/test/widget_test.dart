import 'package:car10th_mobile/app/app.dart';
import 'package:car10th_mobile/app/app_settings.dart';
import 'package:car10th_mobile/app/session.dart';
import 'package:car10th_mobile/data/repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

void main() {
  testWidgets('app starts', (tester) async {
    final settings = AppSettings();
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: settings),
          ChangeNotifierProvider(create: (_) => AppSession(settings: settings)),
          Provider<Repository>(create: (_) => MockRepository()),
        ],
        child: const App(),
      ),
    );

    expect(find.byType(App), findsOneWidget);
  });
}
