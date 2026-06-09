"""triage.py 核心文件处理路径的单元测试。

只测不碰网络的部分：classify 一律用 monkeypatch 替换，
vault 用 tmp_path 临时目录，验证打标/归位/容错/dry-run 的磁盘语义。

运行：cd pipeline && python -m pytest tests/ -v
"""
import sys
from pathlib import Path

import frontmatter
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import triage  # noqa: E402


FAKE_META = {
    "type": "literature",
    "tags": ["测试", "ai"],
    "folder": "10_Notes",
    "summary": "一句话摘要",
}


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """临时 vault，预建扫描目录，classify 不走网络。"""
    for rel in ["00_Inbox", "20_Sources/NotebookLM", "10_Notes"]:
        (tmp_path / rel).mkdir(parents=True)
    monkeypatch.setattr(triage, "VAULT", tmp_path)
    monkeypatch.setattr(triage, "DEEPSEEK_KEY", "test-key")
    monkeypatch.setattr(triage, "classify", lambda content: dict(FAKE_META))
    return tmp_path


def make_note(path: Path, body: str = "正文", **meta) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.dumps(frontmatter.Post(body, **meta)), encoding="utf-8")
    return path


# ---- ensure_defaults：曾因 Post.setdefault 不存在而必然抛错 ----------------

def test_ensure_defaults_notebooklm(vault):
    path = vault / "20_Sources/NotebookLM/briefing.md"
    post = frontmatter.Post("内容")
    triage.ensure_defaults(path, post)
    assert post["type"] == "source"
    assert post["source"] == "notebooklm"


def test_ensure_defaults_keeps_existing(vault):
    path = vault / "20_Sources/NotebookLM/briefing.md"
    post = frontmatter.Post("内容", type="permanent")
    triage.ensure_defaults(path, post)
    assert post["type"] == "permanent"  # 已有值不被覆盖


def test_ensure_defaults_skips_inbox(vault):
    post = frontmatter.Post("内容")
    triage.ensure_defaults(vault / "00_Inbox/x.md", post)
    assert "type" not in post.metadata


# ---- process_one：移动、写回、原地更新 ------------------------------------

def test_process_one_moves_and_marks(vault):
    src = make_note(vault / "00_Inbox/idea.md")
    post = frontmatter.load(src)
    triage.process_one(src, post, dry_run=False)

    assert not src.exists()
    dest = vault / "10_Notes/idea.md"
    assert dest.exists()
    saved = frontmatter.load(dest)
    assert saved["ai_processed"] is True
    assert saved["type"] == "literature"
    assert saved["summary"] == "一句话摘要"
    assert saved["tags"] == ["ai", "测试"]
    assert saved.content.strip() == "正文"


def test_process_one_merges_tags(vault):
    src = make_note(vault / "00_Inbox/idea.md", tags=["已有"])
    post = frontmatter.load(src)
    triage.process_one(src, post, dry_run=False)
    saved = frontmatter.load(vault / "10_Notes/idea.md")
    assert saved["tags"] == ["ai", "已有", "测试"]


def test_process_one_in_place_no_rename(vault, monkeypatch):
    """已在目标目录的文件应原地更新，不能被 unique_path 改名成 -1。"""
    monkeypatch.setattr(
        triage, "classify",
        lambda content: dict(FAKE_META, folder="20_Sources/NotebookLM"),
    )
    src = make_note(vault / "20_Sources/NotebookLM/briefing.md")
    post = frontmatter.load(src)
    triage.process_one(src, post, dry_run=False)

    assert src.exists()
    assert not (vault / "20_Sources/NotebookLM/briefing-1.md").exists()
    saved = frontmatter.load(src)
    assert saved["ai_processed"] is True
    assert saved["source"] == "notebooklm"  # ensure_defaults 生效


def test_process_one_collision_gets_suffix(vault):
    make_note(vault / "10_Notes/idea.md", body="占位")
    src = make_note(vault / "00_Inbox/idea.md")
    triage.process_one(src, frontmatter.load(src), dry_run=False)
    assert (vault / "10_Notes/idea-1.md").exists()
    assert frontmatter.load(vault / "10_Notes/idea.md").content.strip() == "占位"


def test_process_one_dry_run_touches_nothing(vault):
    src = make_note(vault / "00_Inbox/idea.md")
    before = src.read_text(encoding="utf-8")
    triage.process_one(src, frontmatter.load(src), dry_run=True)
    assert src.read_text(encoding="utf-8") == before
    assert not (vault / "10_Notes/idea.md").exists()


def test_process_one_disallowed_folder_falls_back(vault, monkeypatch):
    monkeypatch.setattr(
        triage, "classify",
        lambda content: dict(FAKE_META, folder="../../etc"),
    )
    src = make_note(vault / "00_Inbox/idea.md")
    triage.process_one(src, frontmatter.load(src), dry_run=False)
    assert (vault / "10_Notes/idea.md").exists()  # 非法目录回落到 10_Notes


# ---- run_triage / iter_unprocessed：容错与计数 -----------------------------

def test_run_triage_skips_bad_frontmatter(vault, capsys):
    """一个坏 YAML 文件只跳过自己，不放倒整次运行。"""
    bad = vault / "00_Inbox/bad.md"
    bad.write_text("---\ntitle: [未闭合\n---\n正文\n", encoding="utf-8")
    make_note(vault / "00_Inbox/good.md")

    n = triage.run_triage(dry_run=False)

    assert n == 1
    assert (vault / "10_Notes/good.md").exists()
    assert bad.exists()  # 坏文件原样保留，等人工处理
    assert "frontmatter 解析失败" in capsys.readouterr().err


def test_run_triage_skips_processed(vault):
    make_note(vault / "00_Inbox/done.md", ai_processed=True)
    assert triage.run_triage(dry_run=False) == 0


def test_run_triage_continues_after_classify_error(vault, monkeypatch, capsys):
    calls = {"n": 0}

    def flaky(content):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("API 超时")
        return dict(FAKE_META)

    monkeypatch.setattr(triage, "classify", flaky)
    make_note(vault / "00_Inbox/a.md")
    make_note(vault / "00_Inbox/b.md")

    n = triage.run_triage(dry_run=False)

    assert n == 1  # 第一条失败被跳过，第二条照常处理
    assert "[skip]" in capsys.readouterr().err


# ---- 纯函数 ----------------------------------------------------------------

def test_safe_target_rules():
    assert triage.safe_target("30_Projects", None) == "30_Projects"
    assert triage.safe_target("乱写的", None) == "10_Notes"
    assert triage.safe_target("10_Notes", "notebooklm") == "20_Sources/NotebookLM"
    assert triage.safe_target("60_MOC", "notebooklm") == "60_MOC"


def test_parse_json_plain():
    assert triage._parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_fenced():
    assert triage._parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_with_chatter():
    assert triage._parse_json('好的，结果如下：\n{"a": 1}\n以上。') == {"a": 1}


def test_parse_json_garbage_raises():
    with pytest.raises(ValueError):
        triage._parse_json("模型抽风了，没有 JSON")


def test_write_note_atomic_no_tmp_left(vault):
    dest = vault / "10_Notes/x.md"
    triage.write_note(dest, frontmatter.Post("正文", title="x"))
    assert frontmatter.load(dest)["title"] == "x"
    assert list(vault.rglob("*.triage-tmp")) == []
