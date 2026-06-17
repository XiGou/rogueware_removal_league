#!/usr/bin/env python3
"""Generate the Rogueware Removal League static site.

Data lives in two layers:
- data/projects/<project-slug>.json declares each league project.
- data/submissions/<project-slug>/*.json stores one submission per file.

The generator uses only the Python standard library so GitHub Pages builds stay
small and predictable.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlencode, urlparse

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
PROJECTS_DIR = DATA_DIR / "projects"
SUBMISSIONS_DIR = DATA_DIR / "submissions"
PUBLIC_DIR = ROOT / "public"
ASSETS_SRC = ROOT / "assets"
ASSETS_DST = PUBLIC_DIR / "assets"

PER_PAGE = 50
SITE_NAME = "Rogueware Removal League"
SITE_NAME_CN = "流氓软件卸载竞赛"
SITE_DESCRIPTION = "多个流氓软件卸载挑战项目的静态排行榜总览。"


def resolve_repo_url() -> str:
    explicit_url = os.environ.get("REPO_URL", "").strip()
    if explicit_url:
        return explicit_url.rstrip("/")

    github_repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if github_repository and "/" in github_repository:
        return f"https://github.com/{github_repository}"

    return "https://github.com/XiGou/rogueware_removal_league"


REPO_URL = resolve_repo_url()
ISSUES_URL = f"{REPO_URL}/issues"
PULLS_URL = f"{REPO_URL}/pulls"
NEW_PROJECT_TEMPLATE = "leaderboard_project.yml"
NEW_SUBMISSION_TEMPLATE = "submission.yml"
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")


def issue_form_url(template: str, **params: object) -> str:
    query = {"template": template}
    for key, value in params.items():
        if value not in (None, ""):
            query[key] = str(value)
    return f"{ISSUES_URL}/new?{urlencode(query)}"


NEW_PROJECT_URL = issue_form_url(
    NEW_PROJECT_TEMPLATE,
    title="Project: ",
    category="rogueware removal",
    metric_unit="seconds",
    sort="asc",
)


@dataclass(frozen=True)
class Project:
    slug: str
    name: str
    title: str
    category: str
    download_url: str
    summary: str
    description: str
    metric_label: str
    metric_unit: str
    sort: str
    rules: tuple[str, ...]
    evidence_tips: tuple[str, ...]
    safety_notice: str = ""


@dataclass(frozen=True)
class Submission:
    name: str
    time_seconds: int
    message: str
    evidence_url: str
    steps: tuple[str, ...]
    date: str
    issue_url: str = ""
    pr_url: str = ""


@dataclass(frozen=True)
class ProjectState:
    project: Project
    submissions: tuple[Submission, ...]


def html(value: object) -> str:
    return escape(str(value), quote=True)


def load_json(path: Path) -> object:
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno}") from exc


def validate_text(value: object, field_name: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    text = " ".join(value.strip().split())
    if len(text) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer")
    return text


def validate_url(value: object, field_name: str, required: bool = True) -> str:
    if value in (None, "") and not required:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty URL")

    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must start with http:// or https://")
    return url


def validate_date(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("date must be a YYYY-MM-DD string")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("date must use YYYY-MM-DD format") from exc
    return value


def validate_slug(value: object) -> str:
    slug = validate_text(value, "slug", 40)
    if not SLUG_RE.match(slug):
        raise ValueError("slug must use lowercase letters, numbers, and single hyphens")
    return slug


def validate_sort(value: object) -> str:
    if value not in {"asc", "desc"}:
        raise ValueError("sort must be asc or desc")
    return str(value)


def validate_text_list(value: object, field_name: str, min_items: int, max_items: int, max_length: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array of strings")

    items = tuple(validate_text(item, f"{field_name} item", max_length) for item in value)
    if not min_items <= len(items) <= max_items:
        raise ValueError(f"{field_name} must contain {min_items} to {max_items} items")
    return items


def normalize_project(raw: object, index: int) -> Project:
    if not isinstance(raw, dict):
        raise ValueError(f"project #{index} must be an object")

    try:
        return Project(
            slug=validate_slug(raw.get("slug")),
            name=validate_text(raw.get("name"), "name", 60),
            title=validate_text(raw.get("title"), "title", 80),
            category=validate_text(raw.get("category"), "category", 32),
            download_url=validate_url(raw.get("download_url"), "download_url"),
            summary=validate_text(raw.get("summary"), "summary", 120),
            description=validate_text(raw.get("description"), "description", 240),
            metric_label=validate_text(raw.get("metric_label"), "metric_label", 40),
            metric_unit=validate_text(raw.get("metric_unit"), "metric_unit", 24),
            sort=validate_sort(raw.get("sort", "asc")),
            rules=validate_text_list(raw.get("rules"), "rules", 1, 8, 140),
            evidence_tips=validate_text_list(raw.get("evidence_tips"), "evidence_tips", 1, 8, 140),
            safety_notice=validate_text(raw.get("safety_notice", "请只在可控环境里参赛。"), "safety_notice", 160),
        )
    except ValueError as exc:
        raise ValueError(f"project #{index}: {exc}") from exc


def normalize_steps(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        raise ValueError("steps must be a string or an array of strings")

    steps = tuple(validate_text(step, "each step", 120) for step in items)
    if not 1 <= len(steps) <= 6:
        raise ValueError("steps must contain 1 to 6 items")
    return steps


def normalize_submission(raw: object, label: str) -> Submission:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")

    try:
        seconds = raw["time_seconds"]
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
            raise ValueError("time_seconds must be a positive integer")

        return Submission(
            name=validate_text(raw.get("name"), "name", 40),
            time_seconds=seconds,
            message=validate_text(raw.get("message"), "message", 120),
            evidence_url=validate_url(raw.get("evidence_url"), "evidence_url"),
            steps=normalize_steps(raw.get("steps")),
            date=validate_date(raw.get("date")),
            issue_url=validate_url(raw.get("issue_url"), "issue_url", required=False),
            pr_url=validate_url(raw.get("pr_url"), "pr_url", required=False),
        )
    except KeyError as exc:
        raise ValueError(f"{label}: missing required field {exc.args[0]}") from exc
    except ValueError as exc:
        raise ValueError(f"{label}: {exc}") from exc


def load_projects() -> list[Project]:
    if not PROJECTS_DIR.exists():
        raise SystemExit(f"Missing project registry directory: {PROJECTS_DIR}")
    if not PROJECTS_DIR.is_dir():
        raise SystemExit(f"{PROJECTS_DIR} must be a directory containing one JSON file per project")

    project_files = sorted(PROJECTS_DIR.glob("*.json"))
    if not project_files:
        raise SystemExit(f"No project files found in {PROJECTS_DIR}")

    projects: list[Project] = []
    errors: list[str] = []
    seen: set[str] = set()
    for project_file in project_files:
        try:
            raw_project = load_json(project_file)
            project = normalize_project(raw_project, project_file.name)
            if project_file.stem != project.slug:
                raise ValueError(f"{project_file}: file name must match slug {project.slug}.json")
            if project.slug in seen:
                raise ValueError(f"{project_file}: duplicate slug {project.slug}")
            seen.add(project.slug)
            projects.append(project)
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        print("Invalid project registry:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    return projects


def load_submissions(project: Project) -> tuple[Submission, ...]:
    path = SUBMISSIONS_DIR / project.slug
    if not path.exists():
        raise SystemExit(f"Missing submissions directory for {project.slug}: {path}")
    if not path.is_dir():
        raise SystemExit(f"{path} must be a directory containing one JSON file per submission")

    submissions: list[Submission] = []
    errors: list[str] = []
    for submission_file in sorted(path.glob("*.json")):
        try:
            raw_submission = load_json(submission_file)
            submissions.append(normalize_submission(raw_submission, str(submission_file.relative_to(ROOT))))
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        print(f"Invalid submissions for {project.slug}:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    if project.sort == "desc":
        return tuple(sorted(submissions, key=lambda item: (-item.time_seconds, item.date, item.name.lower())))
    return tuple(sorted(submissions, key=lambda item: (item.time_seconds, item.date, item.name.lower())))


def load_site() -> list[ProjectState]:
    return [ProjectState(project, load_submissions(project)) for project in load_projects()]


def clock_time(seconds: int) -> str:
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def human_time(seconds: int) -> str:
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days} 天")
    if hours:
        parts.append(f"{hours} 小时")
    if minutes:
        parts.append(f"{minutes} 分")
    if secs or not parts:
        parts.append(f"{secs} 秒")
    return "".join(parts)


def display_metric(project: Project, seconds: int) -> str:
    if project.metric_unit == "seconds":
        return clock_time(seconds)
    return f"{seconds:,} {project.metric_unit}"


def display_metric_human(project: Project, seconds: int) -> str:
    if project.metric_unit == "seconds":
        return human_time(seconds)
    return f"{seconds:,} {project.metric_unit}"


def median_metric(project: Project, submissions: tuple[Submission, ...]) -> str:
    if not submissions:
        return "等待首个成绩"

    ordered = sorted(entry.time_seconds for entry in submissions)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        median = ordered[midpoint]
    else:
        median = round((ordered[midpoint - 1] + ordered[midpoint]) / 2)
    return display_metric_human(project, median)


def best_metric(project: Project, submissions: tuple[Submission, ...]) -> str:
    if not submissions:
        return "等待首个成绩"
    return display_metric_human(project, submissions[0].time_seconds)


def latest_date(submissions: tuple[Submission, ...]) -> str:
    return max((entry.date for entry in submissions), default="暂无")


def project_page_href(slug: str, page: int) -> str:
    suffix = "index.html" if page == 1 else f"page{page}.html"
    return f"{slug}/{suffix}"


def submission_issue_url(project: Project) -> str:
    return issue_form_url(
        NEW_SUBMISSION_TEMPLATE,
        title=f"Submission: {project.slug} / ",
        project_slug=project.slug,
        project_title=project.title,
    )


def submission_file_hint(project: Project) -> str:
    return f"data/submissions/{project.slug}/YYYY-MM-DD-handle-issue-N.json"


def page_href(page: int) -> str:
    return "index.html" if page == 1 else f"page{page}.html"


def render_topbar(prefix: str = "", current_project: Project | None = None) -> str:
    brand_href = f"{prefix}index.html"
    if current_project:
        nav_links = f"""
      <a href="{prefix}index.html#projects">项目</a>
      <a href="#leaderboard">排行榜</a>
      <a href="#rules">规则</a>
      <a href="{NEW_PROJECT_URL}" target="_blank" rel="noopener noreferrer">新增项目</a>
        """
    else:
        nav_links = f"""
      <a href="#projects">项目</a>
      <a href="#protocol">规则</a>
      <a href="{NEW_PROJECT_URL}" target="_blank" rel="noopener noreferrer">新增项目</a>
        """

    return f"""
  <header class="topbar">
    <a class="brand" href="{brand_href}" aria-label="{SITE_NAME} 首页">
      <span class="brand-mark">RL</span>
      <span>{SITE_NAME}</span>
    </a>
    <nav class="nav-links" aria-label="主导航">
{nav_links}
    </nav>
  </header>
    """


def render_head(title: str, description: str, prefix: str = "") -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{html(description)}">
  <title>{html(title)}</title>
  <link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="{prefix}assets/style.css">
</head>
"""


def render_site_stats(states: list[ProjectState]) -> str:
    total_projects = len(states)
    total_submissions = sum(len(state.submissions) for state in states)
    active_projects = sum(1 for state in states if state.submissions)
    newest = max((latest_date(state.submissions) for state in states if state.submissions), default="暂无")

    return f"""
      <dl class="stat-grid" aria-label="站点统计">
        <div>
          <dt>竞赛项目</dt>
          <dd>{total_projects}</dd>
        </div>
        <div>
          <dt>总提交</dt>
          <dd>{total_submissions}</dd>
        </div>
        <div>
          <dt>已有成绩项目</dt>
          <dd>{active_projects}</dd>
        </div>
        <div>
          <dt>最近提交</dt>
          <dd>{html(newest)}</dd>
        </div>
      </dl>
    """


def render_project_card(state: ProjectState) -> str:
    project = state.project
    submissions = state.submissions
    top_rows = []
    for rank, entry in enumerate(submissions[:3], start=1):
        top_rows.append(
            f"""
            <li>
              <span class="mini-rank">{rank}</span>
              <span>{html(entry.name)}</span>
              <strong>{html(display_metric(project, entry.time_seconds))}</strong>
            </li>
            """
        )

    if not top_rows:
        top_rows.append('<li class="muted-row">等待首个成绩</li>')

    return f"""
        <article class="project-card">
          <div class="project-card__top">
            <p class="eyebrow">{html(project.category)} / {html(project.metric_label)}</p>
            <h3><a href="{project_page_href(project.slug, 1)}">{html(project.title)}</a></h3>
            <p>{html(project.summary)}</p>
          </div>
          <dl class="project-meta">
            <div>
              <dt>提交</dt>
              <dd>{len(submissions)}</dd>
            </div>
            <div>
              <dt>最佳</dt>
              <dd>{html(best_metric(project, submissions))}</dd>
            </div>
          </dl>
          <ol class="mini-board">
            {"".join(top_rows)}
          </ol>
          <a class="project-card__link" href="{project_page_href(project.slug, 1)}">打开排行榜</a>
        </article>
    """


def render_project_sample() -> str:
    sample = {
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
    return html(json.dumps(sample, ensure_ascii=False, indent=2))


def render_index(states: list[ProjectState], built_at: str) -> str:
    project_cards = "".join(render_project_card(state) for state in states)
    return f"""{render_head(f"{SITE_NAME} - {SITE_NAME_CN}", SITE_DESCRIPTION)}<body>
  <a class="skip-link" href="#projects">跳到项目列表</a>
{render_topbar()}

  <main>
    <section class="hero hero--home" aria-labelledby="page-title">
      <div class="hero-copy">
        <p class="eyebrow">ROGUEWARE REMOVAL / COMMUNITY LEAGUE</p>
        <h1 id="page-title">{SITE_NAME}</h1>
        <p class="dek">{SITE_NAME_CN}：每个项目都有自己的计时规则、证据要求和分页排行榜。新增榜单只需要提交项目元数据和一个空成绩文件。</p>
        <div class="hero-actions">
          <a class="button" href="{NEW_PROJECT_URL}" target="_blank" rel="noopener noreferrer">提交新项目</a>
          <a class="button button--ghost" href="#protocol">查看格式</a>
        </div>
      </div>
{render_site_stats(states)}
    </section>

    <section class="projects-section" id="projects" aria-labelledby="projects-title">
      <div class="section-heading">
        <div>
          <p class="eyebrow">LEAGUE PROJECTS</p>
          <h2 id="projects-title">竞赛项目</h2>
        </div>
        <p>{len(states)} 个项目，按 <code>data/projects/</code> 生成</p>
      </div>
      <div class="project-grid">
        {project_cards}
      </div>
    </section>

    <section class="rules rules--home" id="protocol" aria-labelledby="protocol-title">
      <div class="rules-copy">
        <p class="eyebrow">LEAGUE PROTOCOL</p>
        <h2 id="protocol-title">新增项目流程</h2>
        <ol class="rule-list">
          <li>在 Issue 中说明新榜单要测试什么、如何计时、如何判定完成。</li>
          <li>在 <code>data/projects/&lt;slug&gt;.json</code> 新建一个项目文件，slug 使用小写字母、数字和连字符。</li>
          <li>创建 <code>data/submissions/&lt;slug&gt;/</code> 目录，并放入 <code>.gitkeep</code>。</li>
          <li>运行 <code>python3 generate_site.py</code>，确认总览页和项目页都能生成。</li>
        </ol>
      </div>
      <div class="schema-card" aria-label="项目 JSON 示例">
        <div class="schema-card__bar">
          <span>data/projects/&lt;slug&gt;.json</span>
          <span>PROJECT</span>
        </div>
        <pre><code>{render_project_sample()}</code></pre>
      </div>
    </section>
  </main>

  <footer class="site-footer">
    <span>Generated {html(built_at)}</span>
    <a href="{REPO_URL}" target="_blank" rel="noopener noreferrer">GitHub</a>
  </footer>
</body>
</html>
"""


def render_pagination(page: int, total_pages: int) -> str:
    if total_pages <= 1:
        return ""

    links: list[str] = []
    if page > 1:
        links.append(f'<a class="page-link page-link--wide" href="{page_href(page - 1)}">上一页</a>')

    for current in range(1, total_pages + 1):
        aria = ' aria-current="page"' if current == page else ""
        class_name = "page-link is-active" if current == page else "page-link"
        links.append(f'<a class="{class_name}" href="{page_href(current)}"{aria}>{current}</a>')

    if page < total_pages:
        links.append(f'<a class="page-link page-link--wide" href="{page_href(page + 1)}">下一页</a>')

    return f'<nav class="pagination" aria-label="排行榜分页">{"".join(links)}</nav>'


def render_steps_button(project: Project, entry: Submission, rank: int) -> str:
    steps_payload = html(json.dumps(entry.steps, ensure_ascii=False))
    return f"""
                <button
                  class="steps-button"
                  type="button"
                  data-steps-button
                  data-rank="{rank}"
                  data-runner="{html(entry.name)}"
                  data-metric="{html(display_metric(project, entry.time_seconds))}"
                  data-steps="{steps_payload}"
                  aria-haspopup="dialog"
                  aria-controls="steps-dialog">
                  <span>查看步骤</span>
                  <strong>{len(entry.steps)} 项</strong>
                </button>
    """


def render_steps_dialog() -> str:
    return """
      <dialog class="steps-dialog" id="steps-dialog" data-steps-dialog aria-labelledby="steps-dialog-title">
        <div class="steps-dialog__panel">
          <div class="steps-dialog__header">
            <div>
              <p class="eyebrow">KEY STEPS</p>
              <h3 id="steps-dialog-title">关键步骤</h3>
              <p class="steps-dialog__meta" data-steps-meta></p>
            </div>
            <button class="steps-dialog__close" type="button" data-steps-close aria-label="关闭">×</button>
          </div>
          <ol class="steps-dialog__list" data-steps-list></ol>
        </div>
      </dialog>
    """


def render_submission_row(project: Project, entry: Submission, rank: int) -> str:
    rank_class = "rank"
    if rank == 1:
        rank_class += " rank--first"
    elif rank == 2:
        rank_class += " rank--second"
    elif rank == 3:
        rank_class += " rank--third"

    detail_links = [
        f'<a href="{html(entry.evidence_url)}" target="_blank" rel="noopener noreferrer">证据</a>'
    ]
    if entry.issue_url:
        detail_links.append(
            f'<a href="{html(entry.issue_url)}" target="_blank" rel="noopener noreferrer">Issue</a>'
        )
    if entry.pr_url:
        detail_links.append(f'<a href="{html(entry.pr_url)}" target="_blank" rel="noopener noreferrer">PR</a>')

    return f"""
            <tr>
              <td data-label="名次"><span class="{rank_class}">{rank}</span></td>
              <td data-label="选手">
                <div class="runner">
                  <strong>{html(entry.name)}</strong>
                  <span>“{html(entry.message)}”</span>
                </div>
              </td>
              <td data-label="{html(project.metric_label)}">
                <span class="time">{html(display_metric(project, entry.time_seconds))}</span>
                <span class="seconds">{entry.time_seconds:,}s</span>
              </td>
              <td data-label="关键步骤">{render_steps_button(project, entry, rank)}</td>
              <td data-label="提交">
                <div class="proof-links">{"".join(detail_links)}</div>
                <time datetime="{html(entry.date)}">{html(entry.date)}</time>
              </td>
            </tr>
    """


def render_empty_state(project: Project) -> str:
    return f"""
            <tr>
              <td colspan="5">
                <div class="empty-state">
                  <p class="empty-kicker">NO RUNS LOGGED</p>
                  <h2>首个成绩还空着。</h2>
                  <p>{html(project.summary)} 把 Issue、证据和 PR 一起提交即可上榜。</p>
                  <a class="button" href="#submit">提交首个成绩</a>
                </div>
              </td>
            </tr>
    """


def render_submission_sample(project: Project) -> str:
    sample = {
        "name": "你的名字或 ID",
        "time_seconds": 1234,
        "message": "一句完赛感言，120 字以内",
        "evidence_url": "https://github.com/owner/repo/issues/1",
        "issue_url": "https://github.com/owner/repo/issues/1",
        "pr_url": "https://github.com/owner/repo/pull/2",
        "steps": project.rules[:4],
        "date": "2026-06-11",
    }
    return html(json.dumps(sample, ensure_ascii=False, indent=2))


def render_submission_form(project: Project) -> str:
    direct_issue_url = submission_issue_url(project)
    return f"""
    <section class="submit-section" id="submit" aria-labelledby="submit-title">
      <div class="section-heading">
        <div>
          <p class="eyebrow">SUBMIT RUN</p>
          <h2 id="submit-title">提交成绩</h2>
        </div>
        <p>填写关键字段，Issue 创建后会自动生成 PR</p>
      </div>
      <p class="form-note">这个 Issue 会作为榜单证据链接。详细佐证不影响自动 PR，创建 Issue 后请在评论里补充截图、录屏、测试环境、计时方式和清理确认过程。</p>
      <form class="submission-form" data-submission-form data-issue-base="{html(ISSUES_URL + "/new")}" data-template="{NEW_SUBMISSION_TEMPLATE}" data-project-slug="{html(project.slug)}" data-project-title="{html(project.title)}">
        <label>
          <span>名字或 ID</span>
          <input name="name" autocomplete="nickname" required placeholder="YourName">
        </label>
        <label>
          <span>总耗时</span>
          <input name="elapsed_time" required placeholder="20m 34s / 1234s / 20分34秒">
        </label>
        <label>
          <span>完赛日期</span>
          <input name="date" type="date" required>
        </label>
        <label class="form-wide">
          <span>关键步骤</span>
          <textarea name="key_steps" rows="5" required placeholder="1. 安装完成后开始计时&#10;2. 卸载主程序&#10;3. 清理服务、启动项、计划任务和目录&#10;4. 重启后确认无明显残留"></textarea>
        </label>
        <label class="form-wide">
          <span>完赛感言</span>
          <input name="completion_quote" maxlength="120" required placeholder="It is finally gone.">
        </label>
        <div class="form-actions form-wide">
          <button class="button" type="submit">打开预填 Issue</button>
          <a class="button button--ghost" href="{html(direct_issue_url)}" target="_blank" rel="noopener noreferrer">打开空表单</a>
        </div>
      </form>
    </section>
    """


def render_submission_script() -> str:
    return """
  <script>
    (() => {
      const today = new Date().toISOString().slice(0, 10);
      const parseElapsedSeconds = (rawValue) => {
        const value = String(rawValue || "").trim().toLowerCase().replaceAll("：", ":");
        if (/^\\d+$/.test(value)) {
          return Number(value);
        }

        if (value.includes(":")) {
          const parts = value.split(":");
          if (![2, 3].includes(parts.length) || parts.some((part) => !/^\\d+$/.test(part))) {
            return null;
          }
          const numbers = parts.map(Number);
          if (numbers.length === 2) {
            const [minutes, seconds] = numbers;
            return seconds < 60 ? minutes * 60 + seconds : null;
          }
          const [hours, minutes, seconds] = numbers;
          return minutes < 60 && seconds < 60 ? hours * 3600 + minutes * 60 + seconds : null;
        }

        let seconds = 0;
        let matched = false;
        const leftover = value.replace(
          /(\\d+)\\s*(hours?|hrs?|h|小时|时|minutes?|mins?|m|分钟|分|seconds?|secs?|s|秒)/gi,
          (_, amountText, unitText) => {
            matched = true;
            const amount = Number(amountText);
            const unit = unitText.toLowerCase();
            if (["h", "hr", "hrs", "hour", "hours", "小时", "时"].includes(unit)) {
              seconds += amount * 3600;
            } else if (["m", "min", "mins", "minute", "minutes", "分钟", "分"].includes(unit)) {
              seconds += amount * 60;
            } else {
              seconds += amount;
            }
            return " ";
          },
        );

        if (!matched || leftover.replace(/[\\s,，]+/g, "") !== "") {
          return null;
        }
        return seconds;
      };

      document.querySelectorAll("[data-submission-form]").forEach((form) => {
        const dateInput = form.elements.date;
        const elapsedInput = form.elements.elapsed_time;
        if (dateInput && !dateInput.value) {
          dateInput.value = today;
        }
        elapsedInput.addEventListener("input", () => {
          elapsedInput.setCustomValidity("");
        });

        form.addEventListener("submit", (event) => {
          event.preventDefault();
          const values = new FormData(form);
          const params = new URLSearchParams();
          const slug = form.dataset.projectSlug;
          const name = values.get("name") || "Runner";
          const seconds = parseElapsedSeconds(values.get("elapsed_time"));

          if (!seconds || seconds <= 0) {
            elapsedInput.setCustomValidity("请输入秒数或类似 20m 34s、1:02:03、20分34秒 的耗时");
            elapsedInput.reportValidity();
            return;
          }

          elapsedInput.setCustomValidity("");

          params.set("template", form.dataset.template);
          params.set("title", `Submission: ${slug} / ${name} - ${seconds}s`);
          params.set("project_slug", slug);
          params.set("project_title", form.dataset.projectTitle);
          params.set("time_seconds", String(seconds));

          [
            "name",
            "date",
            "key_steps",
            "completion_quote",
          ].forEach((key) => {
            const value = values.get(key);
            if (value) {
              params.set(key, value);
            }
          });

          window.open(`${form.dataset.issueBase}?${params.toString()}`, "_blank", "noopener");
        });
      });

      const stepsDialog = document.querySelector("[data-steps-dialog]");
      if (stepsDialog) {
        const dialogTitle = stepsDialog.querySelector("#steps-dialog-title");
        const dialogMeta = stepsDialog.querySelector("[data-steps-meta]");
        const stepsList = stepsDialog.querySelector("[data-steps-list]");
        const closeDialog = () => {
          if (typeof stepsDialog.close === "function") {
            stepsDialog.close();
          } else {
            stepsDialog.removeAttribute("open");
          }
        };

        document.querySelectorAll("[data-steps-button]").forEach((button) => {
          button.addEventListener("click", () => {
            let steps = [];
            try {
              steps = JSON.parse(button.dataset.steps || "[]");
            } catch {
              steps = [];
            }

            dialogTitle.textContent = `${button.dataset.runner || "选手"} 的关键步骤`;
            dialogMeta.textContent = `#${button.dataset.rank || "-"} · ${button.dataset.metric || ""}`;
            stepsList.replaceChildren(
              ...steps.map((step) => {
                const item = document.createElement("li");
                item.textContent = step;
                return item;
              })
            );

            if (typeof stepsDialog.showModal === "function") {
              stepsDialog.showModal();
            } else {
              stepsDialog.setAttribute("open", "");
            }
          });
        });

        stepsDialog.querySelectorAll("[data-steps-close]").forEach((button) => {
          button.addEventListener("click", closeDialog);
        });

        stepsDialog.addEventListener("click", (event) => {
          if (event.target === stepsDialog) {
            closeDialog();
          }
        });
      }
    })();
  </script>
    """


def render_rule_items(items: tuple[str, ...]) -> str:
    return "".join(f"<li>{html(item)}</li>" for item in items)


def render_project_page(state: ProjectState, page: int, total_pages: int, built_at: str) -> str:
    project = state.project
    submissions = state.submissions
    total = len(submissions)
    first_rank = (page - 1) * PER_PAGE + 1 if total else 0
    last_rank = min(page * PER_PAGE, total)
    page_entries = submissions[first_rank - 1:last_rank] if total else ()
    rows = (
        "".join(render_submission_row(project, entry, rank) for rank, entry in enumerate(page_entries, start=first_rank))
        if page_entries
        else render_empty_state(project)
    )

    return f"""{render_head(project.title, project.description, prefix="../")}<body>
  <a class="skip-link" href="#leaderboard">跳到排行榜</a>
{render_topbar(prefix="../", current_project=project)}

  <main>
    <section class="hero" aria-labelledby="page-title">
      <div class="hero-copy">
        <p class="eyebrow">{html(project.category)} / {html(project.metric_label)}</p>
        <h1 id="page-title">{html(project.title)}</h1>
        <p class="dek">{html(project.description)}</p>
        <div class="hero-actions">
          <a class="button" href="#submit">提交成绩</a>
          <a class="button button--ghost" href="../index.html#projects">全部项目</a>
        </div>
        <p class="download-warning">
          <strong>高风险下载：</strong>仅限具备隔离测试经验的专业用户在虚拟机或测试机中使用。非专业用户禁止下载或运行，可能损坏设备、破坏系统或造成数据丢失。
          <a href="{html(project.download_url)}" target="_blank" rel="noopener noreferrer">确认风险后打开软件下载</a>
        </p>
      </div>
      <dl class="stat-grid" aria-label="当前统计">
        <div>
          <dt>参赛记录</dt>
          <dd>{total}</dd>
        </div>
        <div>
          <dt>最佳成绩</dt>
          <dd>{html(best_metric(project, submissions))}</dd>
        </div>
        <div>
          <dt>中位成绩</dt>
          <dd>{html(median_metric(project, submissions))}</dd>
        </div>
        <div>
          <dt>最近提交</dt>
          <dd>{html(latest_date(submissions))}</dd>
        </div>
      </dl>
    </section>

    <section class="leaderboard-section" id="leaderboard" aria-labelledby="leaderboard-title">
      <div class="section-heading">
        <div>
          <p class="eyebrow">RANKED BY {html(project.metric_unit.upper())}</p>
          <h2 id="leaderboard-title">排行榜</h2>
        </div>
        <p>{html(first_rank)}-{html(last_rank)} / {html(total)}，每页 {PER_PAGE} 人</p>
      </div>

      <div class="table-wrap">
        <table class="leaderboard-table">
          <thead>
            <tr>
              <th scope="col">名次</th>
              <th scope="col">选手</th>
              <th scope="col">{html(project.metric_label)}</th>
              <th scope="col">关键步骤</th>
              <th scope="col">提交</th>
            </tr>
          </thead>
          <tbody>
{rows}
          </tbody>
        </table>
      </div>
      {render_pagination(page, total_pages)}
      {render_steps_dialog()}
    </section>

{render_submission_form(project)}

    <section class="rules" id="rules" aria-labelledby="rules-title">
      <div class="rules-copy">
        <p class="eyebrow">SUBMISSION PROTOCOL</p>
        <h2 id="rules-title">参赛流程</h2>
        <p class="notice">{html(project.safety_notice)}</p>
        <ol class="rule-list">
          {render_rule_items(project.rules)}
          <li>创建 GitHub Issue 填写榜单核心字段，系统会把该 Issue 作为证据链接，生成 <code>{html(submission_file_hint(project))}</code> 并自动提交 PR；详细佐证请继续发在该 Issue 评论里。</li>
        </ol>
        <h3>证据建议</h3>
        <ul class="tip-list">
          {render_rule_items(project.evidence_tips)}
        </ul>
      </div>
      <div class="schema-card" aria-label="JSON 提交示例">
        <div class="schema-card__bar">
          <span>{html(submission_file_hint(project))}</span>
          <span>SUBMISSION</span>
        </div>
        <pre><code>{render_submission_sample(project)}</code></pre>
      </div>
    </section>
  </main>

  <footer class="site-footer">
    <span>Generated {html(built_at)}</span>
    <a href="{REPO_URL}" target="_blank" rel="noopener noreferrer">GitHub</a>
  </footer>
{render_submission_script()}
</body>
</html>
"""


def build() -> None:
    states = load_site()
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if PUBLIC_DIR.exists():
        shutil.rmtree(PUBLIC_DIR)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    if ASSETS_SRC.exists():
        shutil.copytree(ASSETS_SRC, ASSETS_DST)

    (PUBLIC_DIR / "index.html").write_text(render_index(states, built_at), encoding="utf-8")

    total_submissions = 0
    for state in states:
        total_submissions += len(state.submissions)
        out_dir = PUBLIC_DIR / state.project.slug
        out_dir.mkdir(parents=True, exist_ok=True)
        total_pages = max(1, math.ceil(len(state.submissions) / PER_PAGE))
        for page in range(1, total_pages + 1):
            (out_dir / page_href(page)).write_text(
                render_project_page(state, page, total_pages, built_at),
                encoding="utf-8",
            )

    print(f"Built {len(states)} projects and {total_submissions} submissions into {PUBLIC_DIR}")


if __name__ == "__main__":
    build()
