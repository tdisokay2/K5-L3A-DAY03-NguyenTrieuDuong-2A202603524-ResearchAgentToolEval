from __future__ import annotations

import argparse
import csv
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template_string, request

from chat import now_iso, run_model_tool_loop, safe_slug, trim_history, write_transcript
from env_loader import load_lab_env
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version

ROOT = Path(__file__).parent
ARTIFACTS_DIR = ROOT / "artifacts"
PROMPTS_DIR = ARTIFACTS_DIR / "prompts"
TRANSCRIPTS_DIR = ROOT / "transcripts"
RUNS_DIR = ROOT / "runs"
load_lab_env(ROOT)

app = Flask(__name__)

# Phiên bản prompt & tools preset
PROMPT_PRESETS: dict[str, dict[str, Any]] = {
    "v3": {
        "label": "v3 — Hoàn thiện (Đề xuất)",
        "badge": "Recommended",
        "description": "Đầy đủ rule routing, 2-step Send confirmation guardrail, clarify khi thiếu dữ liệu, chuẩn hóa handle không có @.",
        "prompt_path": PROMPTS_DIR / "system_prompt_v3.md",
        "tools_path": PROMPTS_DIR / "tools_v3.yaml",
    },
    "v2": {
        "label": "v2 — Tool Prerequisite",
        "badge": "High Accuracy",
        "description": "Thêm prerequisite rõ ràng vào mô tả tool trong tools.yaml (chặn đoán mò tài khoản và URL).",
        "prompt_path": PROMPTS_DIR / "system_prompt_v2.md",
        "tools_path": PROMPTS_DIR / "tools_v2.yaml",
    },
    "v1": {
        "label": "v1 — Clarification Prompt",
        "badge": "Prompt-only",
        "description": "Bổ sung rule hỏi lại khi thiếu thông tin trong system prompt; giữ tool declarations của baseline.",
        "prompt_path": PROMPTS_DIR / "system_prompt_v1.md",
        "tools_path": PROMPTS_DIR / "tools_v1.yaml",
    },
    "v0": {
        "label": "v0 — Baseline (Khởi điểm)",
        "badge": "Baseline",
        "description": "Bản mẫu thô ban đầu: khuyến khích đoán mò tham số, gửi ngay không hỏi xác nhận.",
        "prompt_path": PROMPTS_DIR / "system_prompt_v0.md",
        "tools_path": PROMPTS_DIR / "tools_v0.yaml",
    },
}

SESSIONS: dict[str, dict[str, Any]] = {}

DEFAULT_CONFIG: dict[str, Any] = {
    "provider": os.getenv("DEFAULT_PROVIDER", "openrouter"),
    "model": None,
    "version": "v3",
    "history_window": 5,
    "max_tool_rounds": 4,
}


def get_version_paths(version_label: str) -> tuple[Path, Path]:
    preset = PROMPT_PRESETS.get(version_label)
    if preset is None:
        raise ValueError(f"Unknown prompt version: {version_label}")
    for path in (preset["prompt_path"], preset["tools_path"]):
        if not path.is_file():
            raise FileNotFoundError(f"Missing {version_label} snapshot: {path}")
    return preset["prompt_path"], preset["tools_path"]


def create_session(provider_name: str, version_label: str, model_override: str | None = None) -> dict[str, Any]:
    system_prompt_path, tools_path = get_version_paths(version_label)
    system_prompt = system_prompt_path.read_text(encoding="utf-8")
    tool_declarations = load_tool_declarations(tools_path)
    openai_tools = to_openai_tools(tool_declarations)
    provider = make_provider(provider_name)
    selected_model = model_override or getattr(provider, "default_model", None)
    artifact_version = build_artifact_version(version_label, system_prompt_path, tools_path)

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    transcript_id = "_".join([
        safe_slug(version_label),
        safe_slug(provider_name),
        timestamp,
    ])
    transcript_path = TRANSCRIPTS_DIR / f"{transcript_id}.transcript.json"
    transcript: dict[str, Any] = {
        "transcript_id": transcript_id,
        **artifact_version_dict(artifact_version),
        "provider": provider_name,
        "model": selected_model,
        "system_prompt": str(system_prompt_path),
        "tools": str(tools_path),
        "history_window": DEFAULT_CONFIG["history_window"],
        "max_tool_rounds": DEFAULT_CONFIG["max_tool_rounds"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "turns": [],
    }
    session_id = str(uuid.uuid4())
    state = {
        "session_id": session_id,
        "provider_name": provider_name,
        "provider": provider,
        "model": selected_model,
        "version_label": version_label,
        "artifact_version": artifact_version.artifact_version,
        "system_prompt": system_prompt,
        "openai_tools": openai_tools,
        "declared_tools": [
            {"name": t["name"], "description": t.get("description", "")}
            for t in tool_declarations
        ],
        "history": [],
        "turn_index": 0,
        "transcript_path": transcript_path,
        "transcript": transcript,
    }
    SESSIONS[session_id] = state
    return state


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Research Agent Studio — AI Eval & Benchmark</title>
  <!-- Marked.js for fast & standard GitHub Flavored Markdown rendering -->
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    :root {
      --bg-base: #090d16;
      --bg-surface: #0f172a;
      --bg-card: #141f32;
      --bg-card-hover: #1b2840;
      --border: rgba(148, 163, 184, 0.12);
      --border-hover: rgba(56, 189, 248, 0.35);
      --border-focus: #38bdf8;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --text-dim: #64748b;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.15);
      --accent-dark: #0284c7;
      --success: #10b981;
      --success-bg: rgba(16, 185, 129, 0.12);
      --danger: #ef4444;
      --danger-bg: rgba(239, 68, 68, 0.12);
      --warning: #f59e0b;
      --warning-bg: rgba(245, 158, 11, 0.12);
      --info: #6366f1;
      --user-bubble: linear-gradient(135deg, #1e40af, #2563eb);
      --agent-bubble: #121c2e;
      --radius-sm: 6px;
      --radius-md: 10px;
      --radius-lg: 14px;
      --radius-xl: 18px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: var(--bg-base);
      color: var(--text-primary);
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
      -webkit-font-smoothing: antialiased;
    }

    /* Custom Modern Slim Scrollbars */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(148, 163, 184, 0.2); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(148, 163, 184, 0.35); }

    /* Top Navigation Bar */
    header {
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border);
      height: 60px;
      padding: 0 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
      z-index: 10;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 1.05rem;
      font-weight: 700;
      color: #fff;
    }
    .brand-icon {
      width: 34px;
      height: 34px;
      background: linear-gradient(135deg, #0284c7, #38bdf8);
      border-radius: var(--radius-md);
      display: grid;
      place-items: center;
      font-size: 1.15rem;
      box-shadow: 0 2px 10px rgba(56, 189, 248, 0.25);
    }
    .nav-tabs {
      display: flex;
      gap: 6px;
      background: rgba(9, 13, 22, 0.7);
      padding: 4px;
      border-radius: var(--radius-md);
      border: 1px solid var(--border);
    }
    .nav-tab {
      background: transparent;
      border: none;
      color: var(--text-secondary);
      padding: 6px 16px;
      border-radius: var(--radius-sm);
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.18s ease;
    }
    .nav-tab:hover {
      color: var(--text-primary);
    }
    .nav-tab.active {
      background: var(--bg-card);
      color: var(--accent);
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
      border: 1px solid rgba(56, 189, 248, 0.2);
    }

    .top-controls {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.25);
      color: #34d399;
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .status-dot {
      width: 6px;
      height: 6px;
      background: #10b981;
      border-radius: 50%;
      box-shadow: 0 0 8px #10b981;
    }
    .version-selector-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
      background: rgba(9, 13, 22, 0.7);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 5px 12px;
      font-size: 0.82rem;
    }
    .version-selector-wrap label {
      color: var(--text-dim);
      font-weight: 700;
      text-transform: uppercase;
      font-size: 0.7rem;
      letter-spacing: 0.05em;
    }
    select.clean-select {
      background: transparent;
      border: none;
      color: var(--accent);
      font-weight: 600;
      font-size: 0.85rem;
      cursor: pointer;
      outline: none;
    }
    select.clean-select option {
      background: var(--bg-surface);
      color: var(--text-primary);
    }

    /* Content Area */
    .tab-content {
      flex: 1;
      display: none;
      height: calc(100vh - 60px);
      overflow: hidden;
    }
    .tab-content.active {
      display: flex;
    }

    /* TAB 1: Chat UI */
    .chat-layout {
      display: flex;
      width: 100%;
      height: 100%;
    }
    .sidebar {
      width: 320px;
      background: var(--bg-surface);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      padding: 16px;
      gap: 16px;
      overflow-y: auto;
      flex-shrink: 0;
    }
    .sidebar-section-title {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-dim);
      font-weight: 700;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .sample-category {
      margin-bottom: 12px;
    }
    .sample-cat-header {
      font-size: 0.72rem;
      color: var(--text-secondary);
      font-weight: 600;
      margin-bottom: 5px;
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .sample-pill {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      text-align: left;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--border);
      color: var(--text-primary);
      padding: 8px 12px;
      border-radius: var(--radius-md);
      font-size: 0.79rem;
      cursor: pointer;
      margin-bottom: 5px;
      line-height: 1.4;
      transition: all 0.15s ease;
    }
    .sample-pill:hover {
      background: var(--accent-glow);
      border-color: var(--accent);
      transform: translateX(2px);
    }
    .sample-badge {
      font-size: 0.68rem;
      padding: 2px 6px;
      border-radius: 4px;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.06);
      color: var(--text-dim);
      flex-shrink: 0;
      margin-left: 6px;
    }
    .info-card {
      background: rgba(9, 13, 22, 0.6);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 10px 12px;
      font-size: 0.78rem;
      line-height: 1.6;
      color: var(--text-secondary);
    }
    .info-card strong { color: var(--text-primary); }
    .tool-chip-list {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
    }
    .tool-chip {
      background: rgba(56, 189, 248, 0.08);
      border: 1px solid rgba(56, 189, 248, 0.22);
      color: var(--accent);
      padding: 3px 8px;
      border-radius: var(--radius-sm);
      font-size: 0.74rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-weight: 600;
      cursor: default;
      transition: all 0.15s;
    }
    .tool-chip:hover {
      border-color: var(--accent);
      background: rgba(56, 189, 248, 0.15);
    }
    .new-chat-btn {
      margin-top: auto;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      background: linear-gradient(135deg, rgba(56, 189, 248, 0.12), rgba(2, 132, 199, 0.2));
      border: 1px solid rgba(56, 189, 248, 0.4);
      color: var(--accent);
      padding: 10px;
      border-radius: var(--radius-md);
      font-size: 0.84rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .new-chat-btn:hover {
      background: var(--accent);
      color: #090d16;
      box-shadow: 0 4px 14px rgba(56, 189, 248, 0.3);
    }

    /* Main Chat Layout */
    .chat-main {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100%;
      background: var(--bg-base);
    }
    .chat-scroll {
      flex: 1;
      overflow-y: auto;
      padding: 24px 32px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    /* Welcome / Empty state */
    .chat-welcome {
      max-width: 680px;
      margin: 30px auto;
      text-align: center;
      padding: 28px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      box-shadow: 0 8px 30px rgba(0,0,0,0.25);
    }
    .welcome-hero-icon {
      font-size: 2.5rem;
      margin-bottom: 12px;
      display: inline-block;
      animation: floatIcon 3s ease-in-out infinite;
    }
    @keyframes floatIcon {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-6px); }
    }
    .welcome-title {
      font-size: 1.35rem;
      font-weight: 700;
      color: #fff;
      margin-bottom: 8px;
    }
    .welcome-desc {
      font-size: 0.88rem;
      color: var(--text-secondary);
      line-height: 1.6;
      margin-bottom: 24px;
    }
    .quick-start-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
      text-align: left;
    }
    .quick-start-card {
      background: rgba(255, 255, 255, 0.025);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 12px 14px;
      cursor: pointer;
      transition: all 0.18s ease;
    }
    .quick-start-card:hover {
      background: var(--accent-glow);
      border-color: var(--accent);
      transform: translateY(-2px);
    }
    .q-title {
      font-size: 0.84rem;
      font-weight: 700;
      color: #e2e8f0;
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .q-prompt {
      font-size: 0.76rem;
      color: var(--text-dim);
      line-height: 1.4;
    }

    /* Message Rows */
    .message-row {
      display: flex;
      gap: 14px;
      max-width: 88%;
      animation: fadeInMsg 0.2s ease-out;
    }
    @keyframes fadeInMsg {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .message-row.user {
      align-self: flex-end;
      flex-direction: row-reverse;
    }
    .message-row.agent {
      align-self: flex-start;
      width: 100%;
      max-width: 900px;
    }
    .avatar {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      font-size: 0.95rem;
      flex-shrink: 0;
      font-weight: 700;
      box-shadow: 0 2px 8px rgba(0,0,0,0.25);
    }
    .avatar.user-av {
      background: linear-gradient(135deg, #2563eb, #1d4ed8);
      color: #fff;
    }
    .avatar.agent-av {
      background: linear-gradient(135deg, #0369a1, #0284c7);
      color: #fff;
      border: 1px solid rgba(56, 189, 248, 0.4);
    }

    .bubble-wrapper {
      display: flex;
      flex-direction: column;
      gap: 4px;
      max-width: 100%;
    }
    .bubble {
      padding: 16px 20px;
      border-radius: var(--radius-lg);
      font-size: 0.94rem;
      line-height: 1.68;
      position: relative;
      box-shadow: 0 4px 14px rgba(0,0,0,0.2);
    }
    .message-row.user .bubble {
      background: var(--user-bubble);
      color: #fff;
      border-top-right-radius: 4px;
      padding: 12px 18px;
    }
    .message-row.agent .bubble {
      background: var(--agent-bubble);
      border: 1px solid var(--border);
      border-top-left-radius: 4px;
      color: var(--text-primary);
    }

    /* 1. Execution Accordion (Tool Calling Process - Sleek, Uncluttered) */
    .exec-accordion {
      margin-bottom: 14px;
      border-radius: var(--radius-md);
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--border);
      overflow: hidden;
      transition: all 0.2s ease;
    }
    .exec-accordion:hover {
      border-color: rgba(148, 163, 184, 0.25);
    }
    .exec-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 12px;
      cursor: pointer;
      background: rgba(255, 255, 255, 0.02);
      user-select: none;
      font-size: 0.8rem;
    }
    .exec-header:hover {
      background: rgba(255, 255, 255, 0.04);
    }
    .exec-left {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .exec-icon {
      font-size: 0.9rem;
      color: var(--accent);
    }
    .exec-title {
      font-weight: 600;
      color: var(--text-secondary);
    }
    .exec-chips {
      display: flex;
      gap: 4px;
      align-items: center;
    }
    .tool-tag {
      padding: 2px 7px;
      border-radius: 4px;
      font-size: 0.72rem;
      font-weight: 600;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      background: rgba(56, 189, 248, 0.12);
      color: var(--accent);
    }
    .tool-tag.hf_search {
      background: rgba(249, 115, 22, 0.15);
      color: #fb923c;
      border: 1px solid rgba(249, 115, 22, 0.3);
    }
    .tool-tag.clarify {
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
    }
    .tool-tag.send {
      background: rgba(239, 68, 68, 0.15);
      color: #f87171;
    }
    .exec-toggle-btn {
      display: flex;
      align-items: center;
      gap: 4px;
      color: var(--text-dim);
      font-size: 0.74rem;
      font-weight: 500;
    }
    .exec-body {
      padding: 10px 12px;
      border-top: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      gap: 8px;
      background: rgba(9, 13, 22, 0.6);
    }
    .step-item {
      display: flex;
      flex-direction: column;
      gap: 4px;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: var(--radius-sm);
      padding: 8px 10px;
      font-size: 0.78rem;
    }
    .step-head {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .step-num {
      color: var(--text-dim);
      font-weight: 700;
      font-size: 0.72rem;
    }
    .step-args {
      color: var(--text-secondary);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.74rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 520px;
    }
    .step-summary {
      color: var(--text-dim);
      font-size: 0.74rem;
      padding-left: 20px;
    }
    .raw-json-wrap {
      margin-top: 6px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      padding-top: 8px;
    }
    .raw-json-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 4px;
    }
    .raw-json-title {
      font-size: 0.72rem;
      color: var(--text-dim);
      font-weight: 600;
    }
    .copy-raw-btn {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-dim);
      padding: 2px 7px;
      border-radius: 4px;
      font-size: 0.7rem;
      cursor: pointer;
    }
    .copy-raw-btn:hover {
      color: var(--accent);
      border-color: var(--accent);
    }
    pre.raw-json-code {
      background: #060911;
      padding: 8px 10px;
      border-radius: 6px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.72rem;
      color: #94a3b8;
      max-height: 180px;
      overflow-y: auto;
      white-space: pre-wrap;
    }

    /* 2. Action Required Card (Clarify & Guardrail) */
    .action-required-card {
      margin-bottom: 14px;
      border-radius: var(--radius-md);
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .action-required-card.clarify {
      background: rgba(245, 158, 11, 0.08);
      border: 1px solid rgba(245, 158, 11, 0.35);
    }
    .action-required-card.guardrail {
      background: rgba(239, 68, 68, 0.08);
      border: 1px solid rgba(239, 68, 68, 0.35);
    }
    .action-head {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.84rem;
      font-weight: 700;
    }
    .action-head.clarify { color: #f59e0b; }
    .action-head.guardrail { color: #f87171; }
    .action-question {
      font-size: 0.92rem;
      color: #fff;
      line-height: 1.5;
    }
    .quick-actions-grid {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 4px;
    }
    .quick-action-btn {
      background: #f59e0b;
      color: #090d16;
      border: none;
      padding: 7px 14px;
      border-radius: var(--radius-sm);
      font-size: 0.8rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .quick-action-btn:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);
    }
    .quick-action-btn.confirm-btn {
      background: #10b981;
      color: #fff;
    }
    .quick-action-btn.confirm-btn:hover {
      box-shadow: 0 4px 12px rgba(16, 185, 129, 0.35);
    }
    .quick-action-btn.cancel-btn {
      background: rgba(255, 255, 255, 0.08);
      color: var(--text-secondary);
      border: 1px solid var(--border);
    }
    .quick-action-btn.cancel-btn:hover {
      background: rgba(239, 68, 68, 0.15);
      color: #fca5a5;
      border-color: rgba(239, 68, 68, 0.4);
    }

    /* 3. Markdown Formatting Body */
    .markdown-body {
      color: var(--text-primary);
      font-size: 0.94rem;
      line-height: 1.68;
      word-break: break-word;
    }
    .markdown-body h1, .markdown-body h2, .markdown-body h3, .markdown-body h4 {
      color: #fff;
      font-weight: 700;
      margin-top: 16px;
      margin-bottom: 8px;
      line-height: 1.35;
    }
    .markdown-body h1:first-child, .markdown-body h2:first-child, .markdown-body h3:first-child {
      margin-top: 0;
    }
    .markdown-body h1 { font-size: 1.3rem; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
    .markdown-body h2 { font-size: 1.15rem; color: #e2e8f0; }
    .markdown-body h3 { font-size: 1.02rem; color: var(--accent); }
    .markdown-body h4 { font-size: 0.92rem; }
    .markdown-body p {
      margin-bottom: 12px;
    }
    .markdown-body p:last-child {
      margin-bottom: 0;
    }
    .markdown-body ul, .markdown-body ol {
      margin: 8px 0 14px 22px;
    }
    .markdown-body li {
      margin: 4px 0;
    }
    .markdown-body strong {
      color: #fff;
      font-weight: 600;
    }
    .markdown-body a.chat-link, .markdown-body a {
      color: var(--accent);
      text-decoration: none;
      font-weight: 500;
      border-bottom: 1px dotted rgba(56, 189, 248, 0.5);
      transition: all 0.15s;
      display: inline-flex;
      align-items: center;
      gap: 3px;
    }
    .markdown-body a:hover {
      border-bottom-style: solid;
      color: #7dd3fc;
    }
    .link-arrow {
      font-size: 0.75rem;
      color: var(--accent);
      opacity: 0.8;
    }
    .markdown-body blockquote {
      border-left: 3px solid var(--accent);
      background: rgba(56, 189, 248, 0.05);
      padding: 8px 14px;
      margin: 12px 0;
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
      color: #cbd5e1;
      font-style: italic;
    }
    .markdown-body code:not(pre code) {
      background: rgba(56, 189, 248, 0.1);
      color: var(--accent);
      padding: 2px 6px;
      border-radius: 4px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.85em;
    }
    .markdown-body pre {
      background: #070a12;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 12px;
      overflow-x: auto;
      margin: 12px 0;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.82rem;
      line-height: 1.5;
      color: #cbd5e1;
    }
    .markdown-body table {
      width: 100%;
      border-collapse: collapse;
      margin: 14px 0;
      font-size: 0.85rem;
      border-radius: var(--radius-sm);
      overflow: hidden;
      border: 1px solid var(--border);
    }
    .markdown-body th {
      background: #172338;
      color: #e2e8f0;
      text-align: left;
      padding: 8px 12px;
      font-weight: 600;
      border-bottom: 1px solid var(--border);
    }
    .markdown-body td {
      padding: 8px 12px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.08);
    }
    .markdown-body tr:nth-child(even) td {
      background: rgba(255, 255, 255, 0.015);
    }

    /* 4. Verified Sources Section (Source Cards Grid) */
    .sources-card {
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid rgba(148, 163, 184, 0.12);
    }
    .sources-head {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.74rem;
      font-weight: 700;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 10px;
    }
    .sources-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 8px;
    }
    .source-item {
      display: flex;
      align-items: center;
      gap: 8px;
      background: rgba(255, 255, 255, 0.025);
      border: 1px solid var(--border);
      padding: 8px 12px;
      border-radius: var(--radius-sm);
      text-decoration: none;
      color: var(--text-secondary);
      transition: all 0.15s ease;
      overflow: hidden;
    }
    .source-item:hover {
      background: var(--accent-glow);
      border-color: rgba(56, 189, 248, 0.4);
      transform: translateY(-1px);
      color: var(--text-primary);
    }
    .source-icon {
      font-size: 1.05rem;
      flex-shrink: 0;
    }
    .source-info {
      overflow: hidden;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .source-title {
      font-size: 0.76rem;
      font-weight: 600;
      color: #e2e8f0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .source-domain {
      font-size: 0.68rem;
      color: var(--text-dim);
      display: flex;
      align-items: center;
      gap: 3px;
    }

    /* 5. Message Footer */
    .msg-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 12px;
      padding-top: 8px;
      border-top: 1px solid rgba(255, 255, 255, 0.04);
      font-size: 0.72rem;
      color: var(--text-dim);
    }
    .msg-footer-left {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .meta-badge {
      background: rgba(255, 255, 255, 0.05);
      padding: 1px 6px;
      border-radius: 4px;
      font-size: 0.68rem;
      color: var(--text-dim);
    }
    .msg-copy-btn {
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-dim);
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 0.72rem;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      transition: all 0.15s;
    }
    .msg-copy-btn:hover {
      background: rgba(255, 255, 255, 0.05);
      border-color: var(--border);
      color: var(--text-primary);
    }

    /* Typing Indicator (Thinking animation) */
    .typing-wave {
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .typing-wave .dot {
      width: 6px;
      height: 6px;
      background: var(--accent);
      border-radius: 50%;
      animation: wave 1.3s infinite ease-in-out;
    }
    .typing-wave .dot:nth-child(2) { animation-delay: 0.15s; }
    .typing-wave .dot:nth-child(3) { animation-delay: 0.3s; }
    @keyframes wave {
      0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
      30% { transform: translateY(-5px); opacity: 1; }
    }
    .thinking-bubble {
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--text-secondary);
      font-size: 0.85rem;
    }

    /* Chat Input Area */
    .chat-input-area {
      padding: 16px 32px;
      background: var(--bg-surface);
      border-top: 1px solid var(--border);
      display: flex;
      gap: 12px;
      align-items: center;
    }
    .chat-input {
      flex: 1;
      background: var(--bg-base);
      border: 1px solid var(--border);
      color: var(--text-primary);
      padding: 14px 18px;
      border-radius: var(--radius-md);
      font-size: 0.92rem;
      outline: none;
      transition: all 0.15s;
    }
    .chat-input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--accent-glow);
    }
    .send-btn {
      background: linear-gradient(135deg, #0284c7, #38bdf8);
      color: #090d16;
      border: none;
      padding: 0 24px;
      height: 48px;
      border-radius: var(--radius-md);
      font-weight: 700;
      cursor: pointer;
      font-size: 0.92rem;
      transition: all 0.15s;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .send-btn:hover:not(:disabled) {
      box-shadow: 0 4px 16px rgba(56, 189, 248, 0.35);
      transform: translateY(-1px);
    }
    .send-btn:disabled { opacity: 0.5; cursor: not-allowed; }

    /* TAB 2: Compare Versions */
    .compare-container {
      width: 100%;
      height: 100%;
      padding: 24px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    .compare-top-bar {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 16px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 16px;
    }
    .compare-pickers {
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .picker-box {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .picker-box label {
      font-size: 0.72rem;
      text-transform: uppercase;
      font-weight: 700;
      color: var(--text-dim);
    }
    .picker-box select {
      background: var(--bg-base);
      border: 1px solid var(--border);
      color: var(--text-primary);
      padding: 8px 12px;
      border-radius: var(--radius-sm);
      font-size: 0.86rem;
      font-weight: 600;
      outline: none;
    }
    .vs-badge {
      font-size: 0.85rem;
      font-weight: 800;
      color: var(--accent);
      background: rgba(56, 189, 248, 0.12);
      padding: 4px 10px;
      border-radius: 20px;
      margin-top: 14px;
    }

    /* Head-to-Head Cards */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }
    .kpi-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .kpi-title {
      font-size: 0.78rem;
      color: var(--text-dim);
      font-weight: 600;
      text-transform: uppercase;
    }
    .kpi-value-row {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
    }
    .kpi-scores {
      font-size: 1.35rem;
      font-weight: 700;
      color: #fff;
    }
    .kpi-scores small {
      font-size: 0.85rem;
      color: var(--text-secondary);
      font-weight: normal;
    }
    .kpi-delta {
      font-size: 0.82rem;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 6px;
    }
    .kpi-delta.pos { background: var(--success-bg); color: var(--success); }
    .kpi-delta.neg { background: var(--danger-bg); color: var(--danger); }
    .kpi-delta.zero { background: rgba(255,255,255,0.06); color: var(--text-secondary); }

    /* Matrix Table */
    .matrix-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .matrix-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }
    .filter-group {
      display: flex;
      gap: 6px;
    }
    .filter-btn {
      background: var(--bg-base);
      border: 1px solid var(--border);
      color: var(--text-secondary);
      padding: 5px 12px;
      border-radius: var(--radius-sm);
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
    }
    .filter-btn.active {
      background: var(--accent-glow);
      border-color: var(--accent);
      color: var(--accent);
    }
    table.matrix-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.84rem;
    }
    table.matrix-table th {
      text-align: left;
      padding: 10px 12px;
      color: var(--text-dim);
      font-size: 0.74rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      border-bottom: 1px solid var(--border);
    }
    table.matrix-table td {
      padding: 12px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.08);
      vertical-align: top;
    }
    table.matrix-table tr:hover td {
      background: rgba(255, 255, 255, 0.02);
    }
    .status-tag {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 5px;
      font-size: 0.75rem;
      font-weight: 700;
    }
    .status-tag.pass { background: var(--success-bg); color: var(--success); }
    .status-tag.fail { background: var(--danger-bg); color: var(--danger); }
    .diff-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 0.76rem;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
    }
    .diff-badge.improved { background: var(--success-bg); color: var(--success); }
    .diff-badge.regressed { background: var(--danger-bg); color: var(--danger); }
    .diff-badge.same { background: rgba(255,255,255,0.04); color: var(--text-dim); }

    /* TAB 3: Version Log */
    .log-container {
      width: 100%;
      height: 100%;
      padding: 24px;
      overflow-y: auto;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="brand-icon">🔬</div>
      <div>
        <span>Research Agent Studio</span>
        <div style="font-size:0.7rem; font-weight:normal; color:var(--text-dim);">AI Multi-tool Research & Grounding</div>
      </div>
    </div>

    <nav class="nav-tabs">
      <button class="nav-tab active" onclick="switchTab('chat')">💬 Live Chat</button>
      <button class="nav-tab" onclick="switchTab('compare')">⚖️ So Sánh Phiên Bản</button>
      <button class="nav-tab" onclick="switchTab('log')">📋 Version Log</button>
    </nav>

    <div class="top-controls">
      <div class="status-badge" title="Hệ thống sẵn sàng nhận lệnh">
        <span class="status-dot"></span>
        <span>Sẵn sàng</span>
      </div>
      <div class="version-selector-wrap" title="Chọn phiên bản Prompt & Tools">
        <label>Prompt</label>
        <select id="promptVersionSelect" class="clean-select" onchange="handleVersionChange()">
          <option value="v3" selected>v3 (Hoàn thiện - Đề xuất)</option>
          <option value="v2">v2 (Tool Prerequisite)</option>
          <option value="v1">v1 (Clarify Prompt)</option>
          <option value="v0">v0 (Baseline)</option>
        </select>
      </div>
    </div>
  </header>

  <!-- TAB 1: Chat UI -->
  <section id="tab-chat" class="tab-content active">
    <div class="chat-layout">
      <aside class="sidebar">
        <div>
          <div class="sidebar-section-title">📌 Phiên làm việc hiện tại</div>
          <div class="info-card">
            <div><strong>Version:</strong> <span id="infoVersion" style="color:var(--accent);">v3</span></div>
            <div><strong>Model:</strong> <span id="infoModel" style="color:#cbd5e1;">openai/gpt-4o-mini</span></div>
            <div><strong>Log:</strong> <span id="infoLog" style="word-break:break-all; font-size:0.72rem; color:var(--text-dim);">...</span></div>
          </div>
        </div>

        <div>
          <div class="sidebar-section-title">💡 Câu hỏi mẫu thử nghiệm</div>
          
          <div class="sample-category">
            <div class="sample-cat-header">🌐 Tin tức & Web</div>
            <button class="sample-pill" onclick="sendPrompt('Tin tức AI hôm nay có gì nổi bật?')">
              <span>Tin tức AI hôm nay có gì?</span>
              <span class="sample-badge">lookup</span>
            </button>
            <button class="sample-pill" onclick="sendPrompt('Tóm tắt bài này: https://openai.com/index/hello-gpt-4o')">
              <span>Tóm tắt bài viết qua URL</span>
              <span class="sample-badge">fetch</span>
            </button>
          </div>

          <div class="sample-category">
            <div class="sample-cat-header">🐦 Mạng xã hội & Handle</div>
            <button class="sample-pill" onclick="sendPrompt('Tweet mới nhất của Sam Altman là gì?')">
              <span>Tweet mới của Sam Altman?</span>
              <span class="sample-badge">timeline</span>
            </button>
            <button class="sample-pill" onclick="sendPrompt('Mọi người đang bàn gì về GPT-5 trên Twitter?')">
              <span>Tìm kiếm bàn luận Twitter</span>
              <span class="sample-badge">social</span>
            </button>
          </div>

          <div class="sample-category">
            <div class="sample-cat-header">❓ & 🛡️ Guardrails & Clarify</div>
            <button class="sample-pill" onclick="sendPrompt('Tóm tắt 5 tweet mới nhất giúp mình')">
              <span>Thiếu handle tài khoản</span>
              <span class="sample-badge" style="color:#f59e0b;">clarify</span>
            </button>
            <button class="sample-pill" onclick="sendPrompt('Đăng bản tin AI lên Telegram giúp mình')">
              <span>Gửi ra ngoài (Cần duyệt)</span>
              <span class="sample-badge" style="color:#f87171;">guardrail</span>
            </button>
            <button class="sample-pill" onclick="sendPrompt('Theo policy công ty, API key có được đưa vào prompt không?')">
              <span>Tra cứu Policy nội bộ</span>
              <span class="sample-badge">policy</span>
            </button>
          </div>

          <div class="sample-category">
            <div class="sample-cat-header">🤗 Hugging Face & AI Models</div>
            <button class="sample-pill" onclick="sendPrompt('Tìm model Qwen 2.5 trên Hugging Face')">
              <span>Tìm model Qwen 2.5</span>
              <span class="sample-badge" style="color:#fb923c;">hf_search</span>
            </button>
            <button class="sample-pill" onclick="sendPrompt('Tìm dataset tiếng Việt trên Hugging Face')">
              <span>Tìm dataset tiếng Việt</span>
              <span class="sample-badge" style="color:#fb923c;">hf_search</span>
            </button>
          </div>
        </div>

        <div>
          <div class="sidebar-section-title">🔧 Công cụ khả dụng (Declared)</div>
          <div class="tool-chip-list" id="sidebarTools"></div>
        </div>

        <button class="new-chat-btn" onclick="initSession()">
          <span>🔄 Bắt đầu phiên chat mới</span>
        </button>
      </aside>

      <div class="chat-main">
        <div class="chat-scroll" id="chatScroll">
          <!-- Welcome screen -->
          <div class="chat-welcome" id="chatWelcome">
            <div class="welcome-hero-icon">🔬</div>
            <div class="welcome-title">Research Agent Studio</div>
            <div class="welcome-desc">
              Trợ lý nghiên cứu AI thông minh: Tự động phân tích ý định, định tuyến công cụ tra cứu thời gian thực, đối soát nguồn tin cậy và thực thi chốt chặn an toàn (Guardrail).
            </div>
            <div class="quick-start-grid">
              <div class="quick-start-card" onclick="sendPrompt('Tin tức AI hôm nay có gì nổi bật?')">
                <div class="q-title">📰 Điểm tin thời sự</div>
                <div class="q-prompt">Tin tức AI hôm nay có gì nổi bật?</div>
              </div>
              <div class="quick-start-card" onclick="sendPrompt('Tweet mới nhất của Sam Altman là gì?')">
                <div class="q-title">🐦 Theo dõi chuyên gia</div>
                <div class="q-prompt">Tweet mới nhất của Sam Altman là gì?</div>
              </div>
              <div class="quick-start-card" onclick="sendPrompt('Tóm tắt 5 tweet mới nhất giúp mình')">
                <div class="q-title">❓ Kiểm thử hỏi lại</div>
                <div class="q-prompt">Tóm tắt 5 tweet mới (Thiếu handle)</div>
              </div>
              <div class="quick-start-card" onclick="sendPrompt('Đăng bản tin AI lên Telegram giúp mình')">
                <div class="q-title">🛡️ Chốt chặn an toàn</div>
                <div class="q-prompt">Đăng bản tin AI lên Telegram (Send Guardrail)</div>
              </div>
            </div>
          </div>
        </div>

        <form class="chat-input-area" onsubmit="handleChatSubmit(event)">
          <input type="text" id="chatInput" class="chat-input" placeholder="Nhập câu hỏi tra cứu hoặc phản hồi tiếp theo..." autocomplete="off" />
          <button type="submit" id="chatSendBtn" class="send-btn">
            <span>Gửi</span>
            <span>➤</span>
          </button>
        </form>
      </div>
    </div>
  </section>

  <!-- TAB 2: Compare Versions -->
  <section id="tab-compare" class="tab-content">
    <div class="compare-container">
      <div class="compare-top-bar">
        <div class="compare-pickers">
          <div class="picker-box">
            <label>Phiên bản A (Baseline)</label>
            <select id="selectRunA" onchange="runComparison()"></select>
          </div>
          <div class="vs-badge">VS</div>
          <div class="picker-box">
            <label>Phiên bản B (Tối ưu)</label>
            <select id="selectRunB" onchange="runComparison()"></select>
          </div>
        </div>
        <div>
          <button class="sample-pill" style="margin:0; background:var(--accent); color:#090d16; font-weight:700;" onclick="refreshRunList()">
            🔄 Quét lại Runs
          </button>
        </div>
      </div>

      <!-- KPI Head-to-Head Cards -->
      <div class="kpi-grid" id="kpiGrid"></div>

      <!-- Case Diff Matrix Table -->
      <div class="matrix-card">
        <div class="matrix-header">
          <div style="font-weight:700; font-size:1rem; color:#fff;">Chi Tiết Từng Test Case (Matrix Diff)</div>
          <div class="filter-group">
            <button class="filter-btn active" onclick="setMatrixFilter('all', this)">Tất cả (<span id="countAll">0</span>)</button>
            <button class="filter-btn" onclick="setMatrixFilter('improved', this)">Đã cải thiện 🟢 (<span id="countImproved">0</span>)</button>
            <button class="filter-btn" onclick="setMatrixFilter('failed', this)">Còn lỗi 🔴 (<span id="countFailed">0</span>)</button>
          </div>
        </div>

        <table class="matrix-table">
          <thead>
            <tr>
              <th style="width:180px;">Case ID</th>
              <th>Mục Đích Kiểm Thử</th>
              <th style="width:130px;">Phiên bản A</th>
              <th style="width:130px;">Phiên bản B</th>
              <th style="width:150px;">Đánh Giá</th>
            </tr>
          </thead>
          <tbody id="matrixBody"></tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- TAB 3: Version Log -->
  <section id="tab-log" class="tab-content">
    <div class="log-container">
      <div class="matrix-card">
        <div style="font-weight:700; font-size:1.1rem; color:#fff; margin-bottom:8px;">Bảng Lịch Sử Tối Ưu (artifacts/version_log.csv)</div>
        <table class="matrix-table">
          <thead>
            <tr>
              <th>Version</th>
              <th>Artifact Thay Đổi</th>
              <th>Giả Thuyết (Hypothesis)</th>
              <th>Trước</th>
              <th>Sau</th>
              <th>Ghi chú</th>
            </tr>
          </thead>
          <tbody id="versionLogBody"></tbody>
        </table>
      </div>
    </div>
  </section>

  <script>
    let currentSessionId = null;
    let comparisonData = [];
    let currentFilter = 'all';

    // Configure marked renderer for beautiful links
    if (typeof marked !== 'undefined') {
      const renderer = new marked.Renderer();
      const defaultLink = renderer.link.bind(renderer);
      renderer.link = function(href, title, text) {
        const linkHref = typeof href === 'object' ? href.href : href;
        const linkText = typeof href === 'object' ? href.text : text;
        return `<a href="${linkHref}" target="_blank" rel="noopener noreferrer" class="chat-link">${linkText} <span class="link-arrow">↗</span></a>`;
      };
      marked.setOptions({
        renderer: renderer,
        breaks: true,
        gfm: true
      });
    }

    // Comprehensive Fallback Markdown parser (100% offline-safe)
    function parseMarkdown(mdText) {
      if (!mdText) return '';
      if (typeof marked !== 'undefined' && marked.parse) {
        try {
          return marked.parse(mdText);
        } catch (e) {
          console.warn('Marked parse error:', e);
        }
      }
      return fallbackMarkdown(mdText);
    }

    function fallbackMarkdown(text) {
      if (!text) return '';
      let html = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

      // Headings
      html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
      html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
      html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

      // Blockquote
      html = html.replace(/^\> (.*$)/gim, '<blockquote>$1</blockquote>');

      // Bold & Italic
      html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
      html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

      // Links: [text](url)
      html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="chat-link">$1 <span class="link-arrow">↗</span></a>');

      // Inline code
      html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

      // Lists
      html = html.replace(/^\s*[-*]\s+(.*$)/gim, '<li>$1</li>');
      html = html.replace(/^\s*(\d+)\.\s+(.*$)/gim, '<li><strong>$1.</strong> $2</li>');

      // Paragraphs
      const lines = html.split(/\n{2,}/);
      return lines.map(p => {
        p = p.trim();
        if (!p) return '';
        if (p.startsWith('<h') || p.startsWith('<ul>') || p.startsWith('<blockquote') || p.startsWith('<pre>')) return p;
        return `<p>${p.replace(/\n/g, '<br/>')}</p>`;
      }).join('\n');
    }

    function switchTab(tabId) {
      document.querySelectorAll('.nav-tab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      if (tabId === 'chat') {
        document.querySelectorAll('.nav-tab')[0].classList.add('active');
        document.getElementById('tab-chat').classList.add('active');
      } else if (tabId === 'compare') {
        document.querySelectorAll('.nav-tab')[1].classList.add('active');
        document.getElementById('tab-compare').classList.add('active');
        loadRuns();
      } else if (tabId === 'log') {
        document.querySelectorAll('.nav-tab')[2].classList.add('active');
        document.getElementById('tab-log').classList.add('active');
        loadVersionLog();
      }
    }

    async function handleVersionChange() {
      const v = document.getElementById('promptVersionSelect').value;
      await initSession(v);
    }

    async function initSession(versionOverride) {
      const v = versionOverride || document.getElementById('promptVersionSelect').value || 'v3';
      try {
        const res = await fetch('/api/session', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ version: v })
        });
        const data = await res.json();
        currentSessionId = data.session_id;
        document.getElementById('infoVersion').textContent = data.artifact_version;
        document.getElementById('infoModel').textContent = data.model || 'Default';
        document.getElementById('infoLog').textContent = data.transcript_file;

        const toolsDiv = document.getElementById('sidebarTools');
        toolsDiv.innerHTML = '';
        (data.tools || []).forEach(t => {
          const span = document.createElement('span');
          span.className = 'tool-chip';
          span.textContent = t.name;
          span.title = `${t.name}: ${t.description || ''}`;
          toolsDiv.appendChild(span);
        });

        // Reset Chat UI (remove messages and keep welcome card)
        const scroll = document.getElementById('chatScroll');
        if (scroll) {
          scroll.querySelectorAll('.message-row').forEach(r => r.remove());
          const welcome = document.getElementById('chatWelcome');
          if (welcome) welcome.style.display = 'block';
        }
      } catch (e) {
        console.error('Session init error:', e);
      }
    }

    // Helper: Extract Verified Sources from toolEvents & assistantText
    function extractSources(assistantText, toolEvents) {
      const sources = [];
      const seen = new Set();

      function add(title, url, domainName) {
        if (!url || typeof url !== 'string' || !url.startsWith('http')) return;
        const cleanUrl = url.trim();
        if (seen.has(cleanUrl)) return;
        seen.add(cleanUrl);

        let d = domainName;
        if (!d) {
          try {
            d = new URL(cleanUrl).hostname.replace(/^www\./, '');
          } catch (e) {
            d = 'web';
          }
        }
        let t = (title || d || 'Xem tài liệu').trim();
        if (t.length > 60) t = t.substring(0, 57) + '...';
        sources.push({ title: t, url: cleanUrl, domain: d });
      }

      // 1. From toolEvents
      if (Array.isArray(toolEvents)) {
        toolEvents.forEach(ev => {
          const res = ev.result || {};
          if (Array.isArray(res.items)) {
            res.items.forEach(it => add(it.title || it.id, it.url, it.source || (ev.tool === 'hf_search' ? 'huggingface.co' : '')));
          }
          if (res.url) {
            add(res.title || res.url, res.url, res.source);
          }
          if (Array.isArray(res.papers)) {
            res.papers.forEach(p => add(p.title, p.url, 'arxiv.org'));
          }
          if (Array.isArray(res.tweets)) {
            res.tweets.forEach(tw => {
              if (tw.url) add(tw.text ? tw.text.slice(0, 50) + '...' : 'Tweet', tw.url, 'x.com');
            });
          }
        });
      }

      // 2. From markdown links in text
      if (assistantText) {
        const linkRegex = /\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)/g;
        let match;
        while ((match = linkRegex.exec(assistantText)) !== null) {
          add(match[1], match[2]);
        }
      }

      return sources.slice(0, 6);
    }

    function getDomainIcon(domain) {
      if (!domain) return '🌐';
      const d = domain.toLowerCase();
      if (d.includes('youtube')) return '▶️';
      if (d.includes('x.com') || d.includes('twitter')) return '🐦';
      if (d.includes('arxiv')) return '📄';
      if (d.includes('facebook')) return '👥';
      if (d.includes('github')) return '🐙';
      if (d.includes('openai')) return '⚡';
      if (d.includes('huggingface')) return '🤗';
      return '🌐';
    }

    // Helper: Build Accordion for Tool Execution
    function buildAccordion(toolEvents) {
      if (!toolEvents || toolEvents.length === 0) return null;

      const wrap = document.createElement('div');
      wrap.className = 'exec-accordion';

      const uniqueTools = [...new Set(toolEvents.map(e => e.tool))];
      const chipsHtml = uniqueTools.map(t => `<span class="tool-tag ${t}">${t}</span>`).join('');

      wrap.innerHTML = `
        <div class="exec-header" onclick="toggleAccordion(this)">
          <div class="exec-left">
            <span class="exec-icon">⚡</span>
            <span class="exec-title">Quá trình suy luận (${toolEvents.length} bước gọi công cụ)</span>
            <div class="exec-chips">${chipsHtml}</div>
          </div>
          <div class="exec-toggle-btn">
            <span class="toggle-text">Chi tiết</span>
            <span class="toggle-icon">▾</span>
          </div>
        </div>
        <div class="exec-body" style="display:none;">
          <div class="exec-steps">
            ${toolEvents.map((ev, i) => {
              const argsBrief = Object.entries(ev.args || {}).map(([k, v]) => `${k}="${v}"`).join(', ') || 'none';
              const res = ev.result || {};
              let summary = '';
              if (ev.tool === 'hf_search') {
                const count = res.count || (res.items && res.items.length) || 0;
                const rType = res.resource_type === 'datasets' ? 'datasets' : 'models';
                summary = `✓ Tìm thấy ${count} ${rType} trên Hugging Face Hub`;
              }
              else if (res.items) summary = `✓ Tìm thấy ${res.items.length} nguồn tài liệu`;
              else if (res.tweets) summary = `✓ Thu thập ${res.tweets.length} tweets`;
              else if (res.papers) summary = `✓ Tìm thấy ${res.papers.length} bài báo arXiv`;
              else if (res.text) summary = `✓ Đã trích xuất nội dung bài viết`;
              else if (res.awaiting_user) summary = `⚠️ Chờ phản hồi từ người dùng: "${res.question || ''}"`;
              else if (res.error) summary = `❌ Lỗi: ${res.message || res.error}`;
              else summary = `✓ Thực thi hoàn tất`;

              return `
                <div class="step-item">
                  <div class="step-head">
                    <span class="step-num">#${i + 1}</span>
                    <span class="tool-tag ${ev.tool}">${ev.tool}</span>
                    <span class="step-args" title="${argsBrief}">(${argsBrief})</span>
                  </div>
                  <div class="step-summary">${summary}</div>
                </div>
              `;
            }).join('')}
          </div>
          <div class="raw-json-wrap">
            <div class="raw-json-bar">
              <span class="raw-json-title">Raw Execution JSON</span>
              <button class="copy-raw-btn" onclick="copyRawJson(this)">Sao chép JSON</button>
            </div>
            <pre class="raw-json-code">${escapeHtml(JSON.stringify(toolEvents, null, 2))}</pre>
          </div>
        </div>
      `;
      return wrap;
    }

    function toggleAccordion(header) {
      const body = header.nextElementSibling;
      const textSpan = header.querySelector('.toggle-text');
      const iconSpan = header.querySelector('.toggle-icon');
      if (body.style.display === 'none') {
        body.style.display = 'flex';
        textSpan.textContent = 'Thu gọn';
        iconSpan.textContent = '▴';
      } else {
        body.style.display = 'none';
        textSpan.textContent = 'Chi tiết';
        iconSpan.textContent = '▾';
      }
    }

    function escapeHtml(str) {
      return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function showTypingIndicator() {
      const scroll = document.getElementById('chatScroll');
      const row = document.createElement('div');
      row.id = 'agentTypingRow';
      row.className = 'message-row agent';
      row.innerHTML = `
        <div class="avatar agent-av">🤖</div>
        <div class="bubble-wrapper">
          <div class="bubble thinking-bubble">
            <div class="typing-wave">
              <span class="dot"></span>
              <span class="dot"></span>
              <span class="dot"></span>
            </div>
            <span>Trợ lý đang suy nghĩ và tra cứu công cụ phù hợp...</span>
          </div>
        </div>
      `;
      scroll.appendChild(row);
      scroll.scrollTop = scroll.scrollHeight;
    }

    function removeTypingIndicator() {
      const el = document.getElementById('agentTypingRow');
      if (el) el.remove();
    }

    function appendMessage(role, text, activityData, status) {
      const welcome = document.getElementById('chatWelcome');
      if (welcome && role === 'user') {
        welcome.style.display = 'none';
      }

      const scroll = document.getElementById('chatScroll');
      const row = document.createElement('div');
      row.className = `message-row ${role}`;

      const av = document.createElement('div');
      av.className = `avatar ${role === 'user' ? 'user-av' : 'agent-av'}`;
      av.textContent = role === 'user' ? 'U' : '🤖';
      row.appendChild(av);

      const bubbleWrap = document.createElement('div');
      bubbleWrap.className = 'bubble-wrapper';

      const bubble = document.createElement('div');
      bubble.className = 'bubble';

      const now = new Date();
      const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      if (role === 'user') {
        bubble.textContent = text || '';
        bubbleWrap.appendChild(bubble);

        const footer = document.createElement('div');
        footer.className = 'msg-footer';
        footer.style.justifyContent = 'flex-end';
        footer.innerHTML = `<span style="font-size:0.7rem; color:var(--text-dim);">${timeStr}</span>`;
        bubbleWrap.appendChild(footer);
      } else {
        // Agent message
        // 1. Tool execution accordion (clean & collapsible)
        const accordion = buildAccordion(activityData);
        if (accordion) {
          bubble.appendChild(accordion);
        }

        // 2. Action Required Card (Clarify or Guardrail)
        const isClarify = status === 'waiting_for_user';
        if (isClarify) {
          const lastEvent = activityData && activityData[activityData.length - 1];
          const resObj = (lastEvent && lastEvent.result) || {};
          const isGuardrail = resObj.response_type === 'yes_no' || (lastEvent && lastEvent.tool === 'send');

          const actionCard = document.createElement('div');
          actionCard.className = `action-required-card ${isGuardrail ? 'guardrail' : 'clarify'}`;

          let buttonsHtml = '';
          if (resObj.response_type === 'yes_no' || isGuardrail) {
            buttonsHtml = `
              <div class="quick-actions-grid">
                <button class="quick-action-btn confirm-btn" onclick="sendPrompt('Xác nhận đồng ý gửi')">
                  ✅ Xác nhận đồng ý gửi
                </button>
                <button class="quick-action-btn cancel-btn" onclick="sendPrompt('Không, hủy thao tác này giúp mình')">
                  ❌ Hủy bỏ thao tác
                </button>
              </div>
            `;
          } else if (Array.isArray(resObj.options) && resObj.options.length > 0) {
            buttonsHtml = `
              <div class="quick-actions-grid">
                ${resObj.options.map(opt => `
                  <button class="quick-action-btn" onclick="sendPrompt('${escapeHtml(opt)}')">
                    👉 ${escapeHtml(opt)}
                  </button>
                `).join('')}
              </div>
            `;
          }

          actionCard.innerHTML = `
            <div class="action-head ${isGuardrail ? 'guardrail' : 'clarify'}">
              <span>${isGuardrail ? '🛡️ Bảo Vệ Ngoại Vi: Cần Xác Nhận Đăng Tải (Guardrail)' : '❓ Yêu Cầu Bổ Sung Thông Tin'}</span>
            </div>
            <div class="action-question">${escapeHtml(text || 'Vui lòng bổ sung thêm thông tin để tiếp tục.')}</div>
            ${buttonsHtml}
          `;
          bubble.appendChild(actionCard);
        } else {
          // Standard Formatted Markdown Response
          const mdDiv = document.createElement('div');
          mdDiv.className = 'markdown-body';
          mdDiv.innerHTML = parseMarkdown(text || '');
          bubble.appendChild(mdDiv);

          // 3. Verified Sources Card Grid
          const sources = extractSources(text, activityData);
          if (sources.length > 0) {
            const sourcesDiv = document.createElement('div');
            sourcesDiv.className = 'sources-card';
            sourcesDiv.innerHTML = `
              <div class="sources-head">
                <span>📚 Nguồn tham khảo đã kiểm chứng (${sources.length})</span>
              </div>
              <div class="sources-grid">
                ${sources.map(s => `
                  <a href="${s.url}" target="_blank" rel="noopener noreferrer" class="source-item" title="${escapeHtml(s.title)}\n${s.url}">
                    <div class="source-icon">${getDomainIcon(s.domain)}</div>
                    <div class="source-info">
                      <div class="source-title">${escapeHtml(s.title)}</div>
                      <div class="source-domain">${escapeHtml(s.domain)} <span style="font-size:0.65rem;">↗</span></div>
                    </div>
                  </a>
                `).join('')}
              </div>
            `;
            bubble.appendChild(sourcesDiv);
          }
        }

        // 4. Message Action Footer
        const v = document.getElementById('infoVersion').textContent || 'v3';
        const footer = document.createElement('div');
        footer.className = 'msg-footer';
        footer.innerHTML = `
          <div class="msg-footer-left">
            <span>${timeStr}</span>
            <span class="meta-badge">${v}</span>
          </div>
          <div>
            <button class="msg-copy-btn" onclick="copyMessageText(this)">
              <span>📋</span>
              <span>Sao chép</span>
            </button>
          </div>
        `;
        bubble.appendChild(footer);
        bubbleWrap.appendChild(bubble);
      }

      row.appendChild(bubbleWrap);
      scroll.appendChild(row);
      scroll.scrollTop = scroll.scrollHeight;
    }

    function copyMessageText(btn) {
      const bubble = btn.closest('.bubble');
      const mdBody = bubble.querySelector('.markdown-body') || bubble.querySelector('.action-question') || bubble;
      const text = mdBody.innerText || mdBody.textContent || '';
      navigator.clipboard.writeText(text).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = '<span>✓</span><span>Đã chép!</span>';
        btn.style.color = '#10b981';
        setTimeout(() => {
          btn.innerHTML = orig;
          btn.style.color = '';
        }, 2000);
      });
    }

    function copyRawJson(btn) {
      const pre = btn.closest('.raw-json-wrap').querySelector('.raw-json-code');
      navigator.clipboard.writeText(pre.textContent).then(() => {
        const orig = btn.textContent;
        btn.textContent = '✓ Đã chép!';
        setTimeout(() => { btn.textContent = orig; }, 2000);
      });
    }

    async function sendPrompt(text) {
      if (!text.trim()) return;
      if (!currentSessionId) await initSession();

      const input = document.getElementById('chatInput');
      const btn = document.getElementById('chatSendBtn');
      input.value = '';
      input.disabled = true;
      btn.disabled = true;

      appendMessage('user', text);
      showTypingIndicator();

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ session_id: currentSessionId, message: text })
        });
        const data = await res.json();
        removeTypingIndicator();
        appendMessage('agent', data.assistant_text || data.error, data.tool_events, data.status);
      } catch (err) {
        removeTypingIndicator();
        appendMessage('agent', `Lỗi kết nối: ${err.message}`, null, 'error');
      } finally {
        input.disabled = false;
        btn.disabled = false;
        input.focus();
      }
    }

    function handleChatSubmit(e) {
      e.preventDefault();
      const val = document.getElementById('chatInput').value;
      sendPrompt(val);
    }

    // TAB 2: Comparison Logic
    async function loadRuns() {
      try {
        const res = await fetch('/api/runs');
        const runs = await res.json();
        const selA = document.getElementById('selectRunA');
        const selB = document.getElementById('selectRunB');
        selA.innerHTML = '';
        selB.innerHTML = '';

        runs.forEach((r, idx) => {
          const optA = document.createElement('option');
          optA.value = r.file;
          optA.textContent = `${r.version} (${r.suite}) — Acc: ${(r.accuracy * 100).toFixed(0)}% — ${r.file}`;
          selA.appendChild(optA);

          const optB = document.createElement('option');
          optB.value = r.file;
          optB.textContent = optA.textContent;
          selB.appendChild(optB);
        });

        if (runs.length >= 2) {
          selA.selectedIndex = 0;
          selB.selectedIndex = runs.length - 1;
        }
        runComparison();
      } catch (e) {
        console.error('Error loading runs:', e);
      }
    }

    function refreshRunList() {
      loadRuns();
    }

    async function runComparison() {
      const fileA = document.getElementById('selectRunA').value;
      const fileB = document.getElementById('selectRunB').value;
      if (!fileA || !fileB) return;

      try {
        const res = await fetch(`/api/compare?run_a=${encodeURIComponent(fileA)}&run_b=${encodeURIComponent(fileB)}`);
        const data = await res.json();
        renderComparisonKPI(data.summary_a, data.summary_b);
        comparisonData = data.cases || [];
        renderMatrixTable();
      } catch (e) {
        console.error('Comparison error:', e);
      }
    }

    function renderComparisonKPI(sumA, sumB) {
      const grid = document.getElementById('kpiGrid');
      grid.innerHTML = '';

      const metrics = [
        { key: 'case_accuracy', label: 'Case Accuracy', format: v => `${((v || 0) * 100).toFixed(1)}%` },
        { key: 'tool_routing_accuracy', label: 'Tool Routing', format: v => `${((v || 0) * 100).toFixed(1)}%` },
        { key: 'argument_accuracy', label: 'Argument Accuracy', format: v => `${((v || 0) * 100).toFixed(1)}%` },
        { key: 'multiturn_accuracy', label: 'Multiturn Accuracy', format: v => v != null ? `${(v * 100).toFixed(1)}%` : 'N/A' },
      ];

      metrics.forEach(m => {
        const valA = sumA ? sumA[m.key] : 0;
        const valB = sumB ? sumB[m.key] : 0;
        const diff = (valB != null && valA != null) ? (valB - valA) * 100 : 0;
        const deltaClass = diff > 0 ? 'pos' : (diff < 0 ? 'neg' : 'zero');
        const sign = diff > 0 ? '+' : '';

        const card = document.createElement('div');
        card.className = 'kpi-card';
        card.innerHTML = `
          <div class="kpi-title">${m.label}</div>
          <div class="kpi-value-row">
            <div class="kpi-scores">${m.format(valB)} <small>từ ${m.format(valA)}</small></div>
            <div class="kpi-delta ${deltaClass}">${sign}${diff.toFixed(1)}%</div>
          </div>
        `;
        grid.appendChild(card);
      });
    }

    function setMatrixFilter(filter, btn) {
      currentFilter = filter;
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderMatrixTable();
    }

    function renderMatrixTable() {
      const tbody = document.getElementById('matrixBody');
      tbody.innerHTML = '';

      let improvedCount = 0;
      let failedCount = 0;

      comparisonData.forEach(c => {
        if (c.diff_status === 'improved') improvedCount++;
        if (!c.passed_b) failedCount++;
      });

      document.getElementById('countAll').textContent = comparisonData.length;
      document.getElementById('countImproved').textContent = improvedCount;
      document.getElementById('countFailed').textContent = failedCount;

      const filtered = comparisonData.filter(c => {
        if (currentFilter === 'improved') return c.diff_status === 'improved';
        if (currentFilter === 'failed') return !c.passed_b;
        return true;
      });

      filtered.forEach(c => {
        const tr = document.createElement('tr');
        const diffTag = c.diff_status === 'improved'
          ? '<span class="diff-badge improved">🟢 Cải thiện (Fixed)</span>'
          : (c.diff_status === 'regressed'
            ? '<span class="diff-badge regressed">🔴 Thụt lùi (Regressed)</span>'
            : '<span class="diff-badge same">⚪ Giữ nguyên</span>');

        tr.innerHTML = `
          <td><strong>${c.id}</strong></td>
          <td style="color:var(--text-secondary);">${c.what_it_tests || c.skill || ''}</td>
          <td>
            <span class="status-tag ${c.passed_a ? 'pass' : 'fail'}">${c.passed_a ? 'PASS' : 'FAIL'}</span>
            <div style="font-size:0.72rem; color:var(--text-dim); margin-top:2px;">${c.tools_a || 'none'}</div>
          </td>
          <td>
            <span class="status-tag ${c.passed_b ? 'pass' : 'fail'}">${c.passed_b ? 'PASS' : 'FAIL'}</span>
            <div style="font-size:0.72rem; color:var(--text-dim); margin-top:2px;">${c.tools_b || 'none'}</div>
          </td>
          <td>${diffTag}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    // TAB 3: Load Version Log
    async function loadVersionLog() {
      try {
        const res = await fetch('/api/version_log');
        const rows = await res.json();
        const tbody = document.getElementById('versionLogBody');
        tbody.innerHTML = '';
        rows.forEach(r => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td><strong style="color:var(--accent);">${r.version}</strong></td>
            <td><code style="background:rgba(56,189,248,0.1); color:var(--accent); padding:2px 6px; border-radius:4px;">${r.changed_artifact}</code></td>
            <td style="color:var(--text-secondary);">${r.hypothesis || ''}</td>
            <td>${r.metric_before || '-'}</td>
            <td><strong style="color:var(--success);">${r.metric_after || '-'}</strong></td>
            <td style="font-size:0.75rem; color:var(--text-dim);">${r.reason || ''}</td>
          `;
          tbody.appendChild(tr);
        });
      } catch (e) {
        console.error('Error loading version log:', e);
      }
    }

    // Startup
    initSession();
  </script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index() -> str:
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/prompts", methods=["GET"])
def api_prompts():
    data = []
    for key, val in PROMPT_PRESETS.items():
        data.append({
            "key": key,
            "label": val["label"],
            "badge": val["badge"],
            "description": val["description"],
        })
    return jsonify(data)


@app.route("/api/session", methods=["POST"])
def api_create_session():
    payload = request.get_json(silent=True) or {}
    version_label = payload.get("version") or DEFAULT_CONFIG["version"]
    if not isinstance(version_label, str) or version_label not in PROMPT_PRESETS:
        return jsonify({"error": "Unknown prompt version"}), 400

    state = create_session(
        provider_name=DEFAULT_CONFIG["provider"],
        version_label=version_label,
        model_override=DEFAULT_CONFIG["model"],
    )
    return jsonify({
        "session_id": state["session_id"],
        "provider": state["provider_name"],
        "model": state["model"],
        "artifact_version": state["artifact_version"],
        "transcript_file": f"transcripts/{state['transcript_path'].name}",
        "tools": state["declared_tools"],
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    payload = request.get_json(force=True) or {}
    session_id = payload.get("session_id")
    user_text = (payload.get("message") or "").strip()
    if not user_text:
        return jsonify({"status": "provider_error", "error": "Empty message"}), 400

    state = SESSIONS.get(session_id)
    if state is None:
        state = create_session(
            provider_name=DEFAULT_CONFIG["provider"],
            version_label=DEFAULT_CONFIG["version"],
            model_override=DEFAULT_CONFIG["model"],
        )

    state["turn_index"] += 1
    messages = [
        {"role": "system", "content": state["system_prompt"]},
        *trim_history(state["history"], DEFAULT_CONFIG["history_window"]),
        {"role": "user", "content": user_text},
    ]

    turn_record: dict[str, Any] = {
        "turn_index": state["turn_index"],
        "started_at": now_iso(),
        "user": user_text,
        "status": "started",
        "assistant_text": None,
        "rounds": [],
        "tool_events": [],
    }

    try:
        result = run_model_tool_loop(
            provider=state["provider"],
            messages=messages,
            tools=state["openai_tools"],
            model=state["model"],
            max_tool_rounds=DEFAULT_CONFIG["max_tool_rounds"],
        )
        turn_record.update(result)
        assistant_text = result["assistant_text"]
        state["history"].append({"role": "user", "content": user_text})
        state["history"].append({"role": "assistant", "content": assistant_text})
    except Exception as exc:
        turn_record.update({
            "status": "provider_error",
            "error": f"{type(exc).__name__}: {str(exc)}",
        })

    turn_record["ended_at"] = now_iso()
    state["transcript"]["turns"].append(turn_record)
    write_transcript(state["transcript_path"], state["transcript"])

    return jsonify({
        "session_id": state["session_id"],
        "turn_index": turn_record["turn_index"],
        "status": turn_record["status"],
        "assistant_text": turn_record.get("assistant_text"),
        "error": turn_record.get("error"),
        "tool_events": turn_record.get("tool_events", []),
        "transcript_file": f"transcripts/{state['transcript_path'].name}",
    })


@app.route("/api/runs", methods=["GET"])
def api_runs():
    runs = []
    if RUNS_DIR.exists():
        for path in sorted(RUNS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                summary = data.get("summary", {})
                runs.append({
                    "file": path.name,
                    "version": data.get("version", path.stem),
                    "suite": data.get("suite", ""),
                    "accuracy": summary.get("case_accuracy", 0.0),
                    "generated_at": data.get("generated_at", ""),
                })
            except Exception:
                pass
    return jsonify(runs)


@app.route("/api/compare", methods=["GET"])
def api_compare():
    file_a = request.args.get("run_a")
    file_b = request.args.get("run_b")
    if not file_a or not file_b:
        return jsonify({"error": "Missing run_a or run_b parameter"}), 400

    path_a = RUNS_DIR / file_a
    path_b = RUNS_DIR / file_b
    if not path_a.exists() or not path_b.exists():
        return jsonify({"error": "One or both run files not found"}), 404

    data_a = json.loads(path_a.read_text(encoding="utf-8"))
    data_b = json.loads(path_b.read_text(encoding="utf-8"))

    results_a_map = {item["id"]: item for item in data_a.get("results", [])}
    results_b_map = {item["id"]: item for item in data_b.get("results", [])}

    all_ids = sorted(set(results_a_map.keys()) | set(results_b_map.keys()))
    cases = []

    for cid in all_ids:
        item_a = results_a_map.get(cid)
        item_b = results_b_map.get(cid)
        meta = (item_b or item_a or {}).get("metadata", {})

        passed_a = item_a["result"]["passed"] if item_a else False
        passed_b = item_b["result"]["passed"] if item_b else False

        calls_a = ", ".join(c.get("name", "") for c in item_a.get("result", {}).get("actual_tool_calls", [])) if item_a else ""
        calls_b = ", ".join(c.get("name", "") for c in item_b.get("result", {}).get("actual_tool_calls", [])) if item_b else ""

        if not passed_a and passed_b:
            diff_status = "improved"
        elif passed_a and not passed_b:
            diff_status = "regressed"
        else:
            diff_status = "same"

        cases.append({
            "id": cid,
            "skill": meta.get("skill", ""),
            "what_it_tests": meta.get("what_it_tests", ""),
            "passed_a": passed_a,
            "passed_b": passed_b,
            "tools_a": calls_a,
            "tools_b": calls_b,
            "diff_status": diff_status,
        })

    return jsonify({
        "summary_a": data_a.get("summary", {}),
        "summary_b": data_b.get("summary", {}),
        "cases": cases,
    })


@app.route("/api/version_log", methods=["GET"])
def api_version_log():
    log_path = ARTIFACTS_DIR / "version_log.csv"
    if not log_path.exists():
        return jsonify([])

    rows = []
    with log_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return jsonify(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Flask Web UI for Research Agent.")
    parser.add_argument("--provider", choices=["openrouter", "openai", "anthropic", "gemini", "ollama"], default="openrouter")
    parser.add_argument("--model", default=None)
    parser.add_argument("--version", default="v3", help="Artifact version label.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    DEFAULT_CONFIG["provider"] = args.provider
    DEFAULT_CONFIG["model"] = args.model
    DEFAULT_CONFIG["version"] = args.version

    print(f"Starting Research Agent Studio at http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
