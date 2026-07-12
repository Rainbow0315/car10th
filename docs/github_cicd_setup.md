# GitHub 分支与 CI 配置说明

这套方案按你当前的目标设计：

- `main`：受保护主分支，只允许通过 Pull Request 合并
- `dev`：开发分支，普通开发者日常只向这里提交
- GitHub Actions：在 `dev` 推送后自动执行前后端检查
- `dev -> main`：必须经过 CI 通过，再由管理员审核后才能合并

## 先说明一个关键点

GitHub 无法做到“开发者先 push 到 `dev` 之前就先跑 CI 再决定让不让 push”。

当前这套方案的实际效果是：

1. 开发者把代码 push 到 `dev`
2. GitHub Actions 自动运行 CI
3. 只有 CI 通过后，`dev` 才允许发起合并到 `main` 的 Pull Request
4. `main` 分支必须管理员审批后才能合并

如果你后面想做到“代码进入 `dev` 前就先校验”，需要把流程升级成：

- `feature/* -> PR -> dev -> PR -> main`

但就你现在的需求来说，先用 `dev -> main` 这套已经够用了，而且实施成本最低。

## 本仓库已生成的流水线

文件位置：

- `.github/workflows/mobile_app_ci.yml`

触发规则：

- push 到 `dev` 时执行
- PR 指向 `dev` 或 `main` 时执行
- 支持手动触发

检查内容分两部分：

### 前端（Flutter / `mobile_app`）

1. 安装 Flutter stable
2. `flutter pub get`
3. `dart format --set-exit-if-changed`
4. `flutter analyze`
5. `flutter test`
6. `flutter build web --release`

### 后端（Python / `backend`）

1. 安装 Python 3.10
2. `pip install -r backend/requirements.txt`
3. `python -m compileall .`
4. 导入 FastAPI 应用冒烟检查：

```bash
PYTHONPATH=. python -c "from apps.web_api.main import app; print(app.title)"
```

## 第一步：创建并推送 dev 分支

在本地仓库执行：

```bash
git checkout main
git pull origin main
git checkout -b dev
git push -u origin dev
```

说明：

- `dev` 分支应当从当前最新 `main` 拉出来
- 这一步执行后，GitHub 上才会出现 `dev`

## 第二步：把 CI 文件提交到仓库

建议你把这次改动提交到 `main` 后，再推送 `dev`，这样两个分支都会带上同一套工作流文件。

本次需要提交的核心文件：

- `.github/workflows/mobile_app_ci.yml`
- `docs/github_cicd_setup.md`

另外我顺手修了几个 Flutter lint/弃用问题，不然前端这条 CI 会直接失败。

## 第三步：在 GitHub 上保护 main 分支

进入仓库：

- `GitHub 仓库`
- `Settings`
- `Branches`
- `Add branch protection rule`

针对 `main` 填：

### Branch name pattern

```text
main
```

### 建议开启的选项

1. `Require a pull request before merging`
2. `Require approvals`
   - 建议至少 `1`
3. `Dismiss stale pull request approvals when new commits are pushed`
4. `Require status checks to pass before merging`
5. 在状态检查里勾选：
   - `Flutter Quality Gate`
   - `Backend Quality Gate`
6. `Restrict who can push to matching branches`
   - 这里建议只保留管理员

这样配置后：

- 普通开发者不能直接 push `main`
- 必须通过 PR 合并
- 必须先通过前后端 CI
- 必须有人审核

## 第四步：让“管理员审批”真正生效

如果你们仓库里有明确管理员账号，推荐再加一层：

### 方案 A：直接用 GitHub 仓库权限

让普通开发者只拥有 `Write` 权限，让管理员拥有 `Admin` 或 `Maintain` 权限。

然后 `main` 分支设置为：

- 只有管理员允许直接 push
- 普通开发者只能提 PR，不能直接改 `main`

### 方案 B：使用 CODEOWNERS 强制指定审核人

如果你希望必须由指定管理员审核后才能进 `main`，可以再加一个 `.github/CODEOWNERS` 文件，并在 `main` 的保护规则里打开：

- `Require review from Code Owners`

这个方案更严格，但需要你先确定管理员的 GitHub 用户名或团队名。

## 第五步：是否保护 dev 分支

按你当前目标，`dev` 不一定要强制 PR，可以先允许开发者直接 push。

如果你想给 `dev` 加一点保护，建议只做下面两项：

1. 保护 `dev` 分支不被误删
2. 保留 CI 触发，但不要要求 PR

如果将来团队人数变多，再升级成：

- 开发者不能直接 push `dev`
- 必须走 `feature/* -> PR -> dev`

## 推荐日常流程

```text
开发者本地开发
-> push 到 dev
-> GitHub Actions 跑 CI
-> CI 通过
-> 从 dev 提 PR 到 main
-> 管理员审核通过
-> 合并进 main
```

## 你在 GitHub 上重点要检查的两个地方

1. `Actions` 页面能看到 `Project CI` 正常执行
2. `Branches` 里 `main` 的保护规则已启用，并且状态检查至少包含：
   - `Flutter Quality Gate`
   - `Backend Quality Gate`
