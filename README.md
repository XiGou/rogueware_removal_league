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
│   ├── projects.json              # 竞赛项目目录
│   └── submissions/
│       └── wintoolbox.json        # 某个项目的成绩
├── assets/
│   ├── favicon.svg
│   └── style.css
├── generate_site.py
└── public/                        # 生成结果
```

## 提交成绩

1. 打开对应项目页，阅读计时规则和证据建议。
2. 创建 GitHub Issue，写清楚项目 slug、总耗时、环境、关键步骤，并附上截图或录屏链接。
3. Fork 本仓库并新建分支。
4. 编辑 `data/submissions/<slug>.json`，在数组里追加你的记录。
5. 本地运行 `python3 generate_site.py`，确认 JSON 没有格式或校验错误。
6. 提交 PR，标题建议使用 `Add submission: <slug> / YourName - 1234s`。

成绩按 `time_seconds` 排序。默认卸载项目使用秒数，越小越靠前。

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
- `evidence_url`: 可公开访问的证据链接，必须是 `http://` 或 `https://`。
- `steps`: 1 到 6 个关键步骤，可以是字符串数组。
- `date`: 完赛日期，格式为 `YYYY-MM-DD`。

可选字段：

- `issue_url`: 成绩 Issue 链接。
- `pr_url`: 成绩 PR 链接。

## 新增竞赛项目

新增项目需要同时修改两个地方：

1. 在 `data/projects.json` 追加项目元数据。
2. 创建 `data/submissions/<slug>.json`，初始内容为 `[]`。

项目元数据示例：

```json
{
  "slug": "new-tool",
  "name": "new-tool",
  "title": "new-tool Removal Challenge",
  "category": "rogueware removal",
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
