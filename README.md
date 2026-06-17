# Rogueware Removal League

**Rogueware Removal League** 是「流氓软件卸载竞赛」的社区排行榜项目：每个竞赛项目定义一个待挑战目标，参赛者按项目规则计时、提交证据和 PR，最终成绩会展示在 GitHub Pages 静态站里。

当前默认项目是 `wintoolbox` Removal Challenge。后续可以通过 PR 新增更多流氓软件卸载项目。

网站由零依赖 Python 静态生成器构建，生成结果放在 `public/`。

## 安全提醒

请只在你可控的隔离环境里参赛，例如虚拟机、测试机或一次性 Windows 环境。不要在主力电脑、工作电脑或登录了重要账号的环境里安装你不信任的软件。提交截图或录屏前，请遮挡用户名、路径、设备 ID、邮箱、序列号等敏感信息。

## 项目结构

```text
.
├── data/
│   ├── projects/                  # 每个项目一个 JSON 文件
│   │   └── wintoolbox.json
│   └── submissions/
│       └── wintoolbox/            # 某个项目的成绩目录，每条记录一个 JSON
├── assets/
│   ├── favicon.svg
│   └── style.css
├── generate_site.py
└── public/                        # 生成结果
```

## 提交成绩

1. 打开对应项目页，阅读计时规则和证据建议。
2. 点击项目页的“提交成绩”，GitHub Issue 表单会自动预填项目 slug。
3. 在项目页表单里填写名字、总耗时、完赛日期、关键步骤和完赛感言。总耗时支持 `20m 34s`、`1:02:03`、`1234s` 或 `20分34秒`，打开 GitHub Issue 前会被前端转换成秒数。
4. 创建 Issue 后，GitHub Actions 会自动生成单条成绩 JSON 并提交 PR。
5. 在 Issue 评论里补充详细佐证信息，例如截图、录屏、测试环境、计时方式和清理确认过程。

Issue 表单只收集会进入榜单 JSON 的核心字段。自动 PR 会把该 Issue 本身作为 `evidence_url`。详细佐证不会影响自动 PR 生成，请放在 Issue 评论里，方便维护者和其他参赛者复核。

如果自动 PR 没有触发，可以重新打开该 Issue，或在 Issue 评论里单独发送 `/create-submission-pr` 手动触发。

你也可以手动提交 PR：在 `data/submissions/<slug>/` 目录新增一个 JSON 文件，文件名建议使用 `YYYY-MM-DD-seconds-name-issue-N.json`，然后运行 `python3 generate_site.py` 校验。

成绩按 `time_seconds` 排序。GitHub Issue 表单只接受秒数；项目页表单会先把自然耗时转换成秒数再打开 Issue。默认卸载项目越小越靠前。

成绩记录格式：

```json
{
  "name": "你的名字或 ID",
  "time_seconds": 1234,
  "message": "一句完赛感言，120 字以内",
  "evidence_url": "https://github.com/owner/repo/issues/1",
  "issue_url": "https://github.com/owner/repo/issues/1",
  "pr_url": "https://github.com/owner/repo/pull/2",
  "steps": [
    "记录开始计时时间",
    "执行卸载",
    "清理残留项",
    "确认完成并停止计时"
  ],
  "date": "2026-06-11"
}
```

必填字段：

- `name`: 参赛者名称，40 字以内。
- `time_seconds`: 总耗时秒数，正整数。
- `message`: 一句完赛感言，120 字以内。
- `evidence_url`: 可公开访问的证据链接，必须是 `http://` 或 `https://`。通过 Issue 表单提交时会自动使用该 Issue 链接。
- `steps`: 1 到 6 个关键步骤，可以是字符串数组。
- `date`: 完赛日期，格式为 `YYYY-MM-DD`。

可选字段：

- `issue_url`: 成绩 Issue 链接。
- `pr_url`: 成绩 PR 链接。

## 新增竞赛项目

新增项目需要同时修改两个地方：

1. 在 `data/projects/<slug>.json` 新建项目元数据文件。
2. 创建 `data/submissions/<slug>/` 目录，并放入 `.gitkeep`。

也可以先点击首页的“提交新项目”，用结构化 Issue 表单描述 slug、类别、计时规则、证据要求和安全说明。

项目元数据示例：

```json
{
  "slug": "new-tool",
  "name": "new-tool",
  "title": "new-tool Removal Challenge",
  "category": "rogueware removal",
  "download_url": "https://example.com/download",
  "summary": "一句话说明这个流氓软件卸载项目测什么。",
  "description": "更完整的项目说明，写清起点、终点和判定标准。",
  "metric_label": "完全卸载耗时",
  "metric_unit": "seconds",
  "sort": "asc",
  "rules": [
    "安装完成后开始计时。",
    "完成卸载并确认无残留后停止计时。"
  ],
  "evidence_tips": [
    "开始计时截图。",
    "关键清理步骤截图。",
    "最终确认截图。"
  ],
  "safety_notice": "请只在可控隔离环境里参赛。"
}
```

字段要求：

- `slug`: 小写字母、数字和连字符，作为 URL 与成绩文件名。
- `title`: 页面标题，建议使用 `<name> Removal Challenge`。
- `download_url`: 软件官方下载页或安装包链接，必须是 `http://` 或 `https://`。
- `summary`: 项目卡片上的一句话简介。
- `description`: 项目页说明。
- `metric_unit`: 当前建议使用 `seconds`。
- `sort`: `asc` 表示越小越好，`desc` 表示越大越好。
- `rules`: 1 到 8 条参赛规则。
- `evidence_tips`: 1 到 8 条证据建议。

新增项目 PR 标题建议使用 `Add league project: <slug>`。

## 本地开发

```bash
python3 generate_site.py
```

生成后的页面：

- `public/index.html`: Rogueware Removal League 总览。
- `public/<slug>/index.html`: 项目排行榜首页。
- `public/<slug>/page2.html`: 超过 50 条成绩后的分页。

## 部署

默认 GitHub Actions 工作流会在 `main` 分支更新时：

1. 检出代码。
2. 运行 `python3 generate_site.py`。
3. 上传 `public/`。
4. 发布到 GitHub Pages。

CI 会通过 `GITHUB_REPOSITORY` 自动生成 GitHub、Issue 和 PR 链接。本地生成时如需覆盖仓库地址，可以运行：

```bash
REPO_URL=https://github.com/owner/repo python3 generate_site.py
```
