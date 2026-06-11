#!/usr/bin/env python3
"""Generate the Rogueware Removal League static site.

Data lives in two layers:
- data/projects.json declares the league projects.
- data/submissions/<project-slug>.json stores submissions for each project.

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
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
PROJECTS_FILE = DATA_DIR / "projects.json"
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
NEW_PROJECT_URL = f"{ISSUES_URL}/new?template=leaderboard_project.md"
NEW_SUBMISSION_URL = f"{ISSUES_URL}/new?template=submission.md"
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")


@dataclass(frozen=True)
class Project:
    slug: str
    name: str
    title: str
    category: str
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


def normalize_submission(raw: object, index: int) -> Submission:
    if not isinstance(raw, dict):
        raise ValueError(f"entry #{index} must be an object")

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
        raise ValueError(f"entry #{index} is missing required field {exc.args[0]}") from exc
    except ValueError as exc:
        raise ValueError(f"entry #{index}: {exc}") from exc


def load_projects() -> list[Project]:
    if not PROJECTS_FILE.exists():
        raise SystemExit(f"Missing project registry: {PROJECTS_FILE}")

    raw_projects = load_json(PROJECTS_FILE)
    if not isinstance(raw_projects, list):
        raise SystemExit(f"{PROJECTS_FILE} must contain a JSON array")

    projects: list[Project] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, raw_project in enumerate(raw_projects, start=1):
        try:
            project = normalize_project(raw_project, index)
            if project.slug in seen:
                raise ValueError(f"project #{index}: duplicate slug {project.slug}")
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
    path = SUBMISSIONS_DIR / f"{project.slug}.json"
    if not path.exists():
        raise SystemExit(f"Missing submissions file for {project.slug}: {path}")

    raw_submissions = load_json(path)
    if not isinstance(raw_submissions, list):
        raise SystemExit(f"{path} must contain a JSON array")

    submissions: list[Submission] = []
    errors: list[str] = []
    for index, raw_submission in enumerate(raw_submissions, start=1):
        try:
            submissions.append(normalize_submission(raw_submission, index))
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
        <p>{len(states)} 个项目，按 <code>data/projects.json</code> 生成</p>
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
          <li>在 <code>data/projects.json</code> 追加一个项目对象，slug 使用小写字母、数字和连字符。</li>
          <li>创建 <code>data/submissions/&lt;slug&gt;.json</code>，初始内容为 <code>[]</code>。</li>
          <li>运行 <code>python3 generate_site.py</code>，确认总览页和项目页都能生成。</li>
        </ol>
      </div>
      <div class="schema-card" aria-label="项目 JSON 示例">
        <div class="schema-card__bar">
          <span>data/projects.json</span>
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


def render_steps(steps: tuple[str, ...]) -> str:
    items = "".join(f"<li>{html(step)}</li>" for step in steps)
    return f'<ol class="steps">{items}</ol>'


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
              <td data-label="关键步骤">{render_steps(entry.steps)}</td>
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
                  <a class="button" href="{NEW_SUBMISSION_URL}" target="_blank" rel="noopener noreferrer">创建成绩 Issue</a>
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
          <a class="button" href="{NEW_SUBMISSION_URL}" target="_blank" rel="noopener noreferrer">提交成绩</a>
          <a class="button button--ghost" href="../index.html#projects">全部项目</a>
        </div>
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
    </section>

    <section class="rules" id="rules" aria-labelledby="rules-title">
      <div class="rules-copy">
        <p class="eyebrow">SUBMISSION PROTOCOL</p>
        <h2 id="rules-title">参赛流程</h2>
        <p class="notice">{html(project.safety_notice)}</p>
        <ol class="rule-list">
          {render_rule_items(project.rules)}
          <li>创建 GitHub Issue 写明耗时、证据、关键步骤，再提交 PR 修改 <code>data/submissions/{html(project.slug)}.json</code>。</li>
        </ol>
        <h3>证据建议</h3>
        <ul class="tip-list">
          {render_rule_items(project.evidence_tips)}
        </ul>
      </div>
      <div class="schema-card" aria-label="JSON 提交示例">
        <div class="schema-card__bar">
          <span>data/submissions/{html(project.slug)}.json</span>
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
