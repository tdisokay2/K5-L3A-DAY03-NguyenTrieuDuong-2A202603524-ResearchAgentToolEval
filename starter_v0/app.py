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
        "prompt_path": PROMPTS_DIR / "system_prompt_v3.md" if (PROMPTS_DIR / "system_prompt_v3.md").exists() else ARTIFACTS_DIR / "system_prompt.md",
        "tools_path": PROMPTS_DIR / "tools_v3.yaml" if (PROMPTS_DIR / "tools_v3.yaml").exists() else ARTIFACTS_DIR / "tools.yaml",
    },
    "v2": {
        "label": "v2 — Tool Prerequisite",
        "badge": "High Accuracy",
        "description": "Thêm prerequisite rõ ràng vào mô tả tool trong tools.yaml (chặn đoán mò tài khoản và URL).",
        "prompt_path": PROMPTS_DIR / "system_prompt_v2.md" if (PROMPTS_DIR / "system_prompt_v2.md").exists() else ARTIFACTS_DIR / "system_prompt.md",
        "tools_path": PROMPTS_DIR / "tools_v3.yaml" if (PROMPTS_DIR / "tools_v3.yaml").exists() else ARTIFACTS_DIR / "tools.yaml",
    },
    "v1": {
        "label": "v1 — Clarification Prompt",
        "badge": "Prompt-only",
        "description": "Bổ sung rule hỏi lại khi thiếu thông tin trong system prompt, từ chối câu ngoài phạm vi.",
        "prompt_path": PROMPTS_DIR / "system_prompt_v1.md" if (PROMPTS_DIR / "system_prompt_v1.md").exists() else ARTIFACTS_DIR / "system_prompt.md",
        "tools_path": ARTIFACTS_DIR / "tools.yaml",
    },
    "v0": {
        "label": "v0 — Baseline (Khởi điểm)",
        "badge": "Baseline",
        "description": "Bản mẫu thô ban đầu: khuyến khích đoán mò tham số, gửi ngay không hỏi xác nhận.",
        "prompt_path": PROMPTS_DIR / "system_prompt_v0.md" if (PROMPTS_DIR / "system_prompt_v0.md").exists() else ARTIFACTS_DIR / "system_prompt.md",
        "tools_path": ARTIFACTS_DIR / "tools.yaml",
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
    if preset:
        p_path = preset["prompt_path"]
        t_path = preset["tools_path"]
        if p_path.exists() and t_path.exists():
            return p_path, t_path
    return ARTIFACTS_DIR / "system_prompt.md", ARTIFACTS_DIR / "tools.yaml"


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


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Research Agent Studio — AI Eval & Benchmark</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: #131c31;
      --card-hover: #1a2642;
      --border: #23304c;
      --border-focus: #38bdf8;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.15);
      --success: #10b981;
      --success-bg: rgba(16, 185, 129, 0.12);
      --danger: #ef4444;
      --danger-bg: rgba(239, 68, 68, 0.12);
      --warning: #f59e0b;
      --warning-bg: rgba(245, 158, 11, 0.12);
      --user-bubble: #1d4ed8;
      --agent-bubble: #182238;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }

    /* Top Navigation Bar */
    header {
      background: var(--card-bg);
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
      width: 32px;
      height: 32px;
      background: linear-gradient(135deg, #0284c7, #38bdf8);
      border-radius: 8px;
      display: grid;
      place-items: center;
      font-size: 1.1rem;
    }
    .nav-tabs {
      display: flex;
      gap: 6px;
      background: rgba(11, 15, 25, 0.6);
      padding: 4px;
      border-radius: 10px;
      border: 1px solid var(--border);
    }
    .nav-tab {
      background: transparent;
      border: none;
      color: var(--text-muted);
      padding: 6px 16px;
      border-radius: 7px;
      font-size: 0.86rem;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.18s ease;
    }
    .nav-tab:hover {
      color: var(--text);
    }
    .nav-tab.active {
      background: var(--card-bg);
      color: var(--accent);
      box-shadow: 0 2px 8px rgba(0,0,0,0.25);
    }

    .top-controls {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .version-selector-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
      background: rgba(11, 15, 25, 0.7);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 4px 10px;
      font-size: 0.82rem;
    }
    .version-selector-wrap label {
      color: var(--text-dim);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 0.7rem;
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
      background: var(--card-bg);
      color: var(--text);
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
      width: 300px;
      background: var(--card-bg);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      padding: 18px;
      gap: 18px;
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
    }
    .sample-pill {
      display: block;
      width: 100%;
      text-align: left;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 0.8rem;
      cursor: pointer;
      margin-bottom: 6px;
      line-height: 1.4;
      transition: all 0.15s ease;
    }
    .sample-pill:hover {
      background: var(--accent-glow);
      border-color: var(--accent);
      transform: translateX(2px);
    }
    .info-card {
      background: rgba(11, 15, 25, 0.6);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 0.78rem;
      line-height: 1.5;
      color: var(--text-muted);
    }
    .info-card strong { color: var(--text); }
    .tool-chip-list {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
    }
    .tool-chip {
      background: rgba(56, 189, 248, 0.08);
      border: 1px solid rgba(56, 189, 248, 0.25);
      color: var(--accent);
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 0.74rem;
      font-family: monospace;
      font-weight: 600;
    }

    .chat-main {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100%;
      background: var(--bg);
    }
    .chat-scroll {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .message-row {
      display: flex;
      gap: 12px;
      max-width: 85%;
    }
    .message-row.user {
      align-self: flex-end;
      flex-direction: row-reverse;
    }
    .message-row.agent {
      align-self: flex-start;
    }
    .avatar {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      font-size: 0.9rem;
      flex-shrink: 0;
      font-weight: 700;
    }
    .avatar.user-av { background: #2563eb; color: #fff; }
    .avatar.agent-av { background: #0369a1; color: #fff; border: 1px solid var(--accent); }
    .bubble {
      padding: 12px 16px;
      border-radius: 12px;
      font-size: 0.92rem;
      line-height: 1.55;
      position: relative;
    }
    .message-row.user .bubble {
      background: var(--user-bubble);
      color: #fff;
      border-top-right-radius: 2px;
    }
    .message-row.agent .bubble {
      background: var(--agent-bubble);
      border: 1px solid var(--border);
      border-top-left-radius: 2px;
    }
    .bubble.clarify-state {
      background: #271e0c;
      border: 1px solid #d97706;
    }

    /* Modern Activity Capsule for Tool Calls (Clean, No JSON spam) */
    .activity-capsule {
      margin-top: 10px;
      background: rgba(11, 15, 25, 0.7);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 0.8rem;
    }
    .activity-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: var(--accent);
      font-weight: 600;
    }
    .activity-items {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-top: 6px;
    }
    .activity-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: #cbd5e1;
      font-size: 0.77rem;
    }
    .activity-badge code {
      background: rgba(56, 189, 248, 0.12);
      color: var(--accent);
      padding: 1px 6px;
      border-radius: 4px;
      font-weight: 600;
    }
    .json-toggle-btn {
      background: transparent;
      border: none;
      color: var(--text-dim);
      font-size: 0.74rem;
      cursor: pointer;
      text-decoration: underline;
    }
    .json-toggle-btn:hover { color: var(--accent); }
    .json-details {
      margin-top: 8px;
      background: #060911;
      padding: 8px;
      border-radius: 6px;
      font-family: Consolas, monospace;
      font-size: 0.72rem;
      color: #94a3b8;
      white-space: pre-wrap;
      display: none;
      max-height: 200px;
      overflow-y: auto;
    }

    .quick-action-bar {
      margin-top: 10px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .quick-btn {
      background: var(--accent);
      color: #0b0f19;
      border: none;
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
      transition: transform 0.1s;
    }
    .quick-btn:hover { transform: scale(1.02); }

    .chat-input-area {
      padding: 16px 24px;
      background: var(--card-bg);
      border-top: 1px solid var(--border);
      display: flex;
      gap: 10px;
    }
    .chat-input {
      flex: 1;
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 12px 16px;
      border-radius: 10px;
      font-size: 0.92rem;
      outline: none;
      transition: border-color 0.15s;
    }
    .chat-input:focus { border-color: var(--accent); }
    .send-btn {
      background: linear-gradient(135deg, #0284c7, #38bdf8);
      color: #0b0f19;
      border: none;
      padding: 0 24px;
      border-radius: 10px;
      font-weight: 700;
      cursor: pointer;
      font-size: 0.92rem;
      transition: opacity 0.15s;
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
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
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
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 8px 12px;
      border-radius: 8px;
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
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
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
      color: var(--text-muted);
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
    .kpi-delta.zero { background: rgba(255,255,255,0.06); color: var(--text-muted); }

    /* Matrix Table */
    .matrix-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
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
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 5px 12px;
      border-radius: 6px;
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
      border-bottom: 1px solid rgba(35, 48, 76, 0.4);
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
      <div>Research Agent Studio</div>
    </div>

    <nav class="nav-tabs">
      <button class="nav-tab active" onclick="switchTab('chat')">💬 Live Chat</button>
      <button class="nav-tab" onclick="switchTab('compare')">⚖️ So Sánh Phiên Bản</button>
      <button class="nav-tab" onclick="switchTab('log')">📋 Version Log</button>
    </nav>

    <div class="top-controls">
      <div class="version-selector-wrap" title="Chọn phiên bản Prompt & Tools để chat">
        <label>Prompt Version</label>
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
          <div class="sidebar-section-title">Phiên làm việc hiện tại</div>
          <div class="info-card">
            <div><strong>Version:</strong> <span id="infoVersion" style="color:var(--accent);">v3</span></div>
            <div><strong>Model:</strong> <span id="infoModel">openai/gpt-4o-mini</span></div>
            <div><strong>Log:</strong> <span id="infoLog" style="word-break:break-all;">...</span></div>
          </div>
        </div>

        <div>
          <div class="sidebar-section-title">Câu hỏi mẫu thử nghiệm</div>
          <button class="sample-pill" onclick="sendPrompt('Tin tức AI hôm nay có gì nổi bật?')">📰 Tin tức AI hôm nay có gì nổi bật?</button>
          <button class="sample-pill" onclick="sendPrompt('Tweet mới nhất của Sam Altman là gì?')">🐦 Tweet mới nhất của Sam Altman?</button>
          <button class="sample-pill" onclick="sendPrompt('Tóm tắt 5 tweet mới nhất giúp mình')">❓ Tóm tắt 5 tweet mới (Thiếu handle)</button>
          <button class="sample-pill" onclick="sendPrompt('Đăng bản tin AI lên Telegram giúp mình')">🛡️ Đăng bản tin Telegram (Cần xác nhận)</button>
          <button class="sample-pill" onclick="sendPrompt('Theo policy công ty, API key có được đưa vào prompt không?')">🔒 Tra cứu Policy (Data Privacy)</button>
        </div>

        <div>
          <div class="sidebar-section-title">Công cụ khả dụng (Declared Tools)</div>
          <div class="tool-chip-list" id="sidebarTools"></div>
        </div>

        <button class="sample-pill" style="margin-top:auto; text-align:center; border-color:var(--accent); color:var(--accent);" onclick="initSession()">
          🔄 Bắt đầu phiên chat mới
        </button>
      </aside>

      <div class="chat-main">
        <div class="chat-scroll" id="chatScroll">
          <div class="message-row agent">
            <div class="avatar agent-av">🤖</div>
            <div class="bubble">
              Xin chào! Tôi là Research Agent. Bạn có thể gõ câu hỏi hoặc bấm các câu hỏi mẫu bên trái để kiểm tra khả năng định tuyến công cụ (Tool Calling).
            </div>
          </div>
        </div>

        <form class="chat-input-area" onsubmit="handleChatSubmit(event)">
          <input type="text" id="chatInput" class="chat-input" placeholder="Nhập câu hỏi tra cứu hoặc phản hồi..." autocomplete="off" />
          <button type="submit" id="chatSendBtn" class="send-btn">Gửi</button>
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
          <button class="sample-pill" style="margin:0; background:var(--accent); color:#0b0f19; font-weight:700;" onclick="refreshRunList()">
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
              <th style="width:140px;">Đánh Giá</th>
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
          span.title = t.description;
          toolsDiv.appendChild(span);
        });
      } catch (e) {
        console.error('Session init error:', e);
      }
    }

    function appendMessage(role, text, activityData, status) {
      const scroll = document.getElementById('chatScroll');
      const row = document.createElement('div');
      row.className = `message-row ${role}`;

      const av = document.createElement('div');
      av.className = `avatar ${role === 'user' ? 'user-av' : 'agent-av'}`;
      av.textContent = role === 'user' ? 'U' : '🤖';
      row.appendChild(av);

      const bubble = document.createElement('div');
      bubble.className = `bubble ${status === 'waiting_for_user' ? 'clarify-state' : ''}`;
      bubble.textContent = text || '';

      // Clean Activity Capsule (No raw JSON dump)
      if (activityData && activityData.length > 0) {
        const capsule = document.createElement('div');
        capsule.className = 'activity-capsule';

        const head = document.createElement('div');
        head.className = 'activity-header';
        head.innerHTML = `<span>⚡ Đã gọi ${activityData.length} công cụ</span>`;

        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'json-toggle-btn';
        toggleBtn.textContent = 'Xem chi tiết JSON ▼';
        toggleBtn.onclick = () => {
          const d = capsule.querySelector('.json-details');
          if (d.style.display === 'block') {
            d.style.display = 'none';
            toggleBtn.textContent = 'Xem chi tiết JSON ▼';
          } else {
            d.style.display = 'block';
            toggleBtn.textContent = 'Thu gọn ▲';
          }
        };
        head.appendChild(toggleBtn);
        capsule.appendChild(head);

        const itemsBox = document.createElement('div');
        itemsBox.className = 'activity-items';
        activityData.forEach(ev => {
          const b = document.createElement('div');
          b.className = 'activity-badge';
          const argsBrief = Object.entries(ev.args || {}).map(([k, val]) => `${k}="${val}"`).slice(0, 3).join(', ');
          b.innerHTML = `<span>🔧</span> <code>${ev.tool}</code> (${argsBrief || 'no args'})`;
          itemsBox.appendChild(b);
        });
        capsule.appendChild(itemsBox);

        const detailsPre = document.createElement('pre');
        detailsPre.className = 'json-details';
        detailsPre.textContent = JSON.stringify(activityData, null, 2);
        capsule.appendChild(detailsPre);

        bubble.appendChild(capsule);

        // Check if clarify waiting_for_user for quick buttons
        const lastEvent = activityData[activityData.length - 1];
        const resObj = (lastEvent && lastEvent.result) || {};
        if (resObj.awaiting_user) {
          const qBox = document.createElement('div');
          qBox.className = 'quick-action-bar';
          if (resObj.response_type === 'yes_no') {
            ['Xác nhận đồng ý gửi', 'Không, hủy giúp mình'].forEach(btnLabel => {
              const qBtn = document.createElement('button');
              qBtn.className = 'quick-btn';
              qBtn.textContent = btnLabel;
              qBtn.onclick = () => sendPrompt(btnLabel);
              qBox.appendChild(qBtn);
            });
          }
          if (qBox.children.length > 0) bubble.appendChild(qBox);
        }
      }

      row.appendChild(bubble);
      scroll.appendChild(row);
      scroll.scrollTop = scroll.scrollHeight;
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

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ session_id: currentSessionId, message: text })
        });
        const data = await res.json();
        appendMessage('agent', data.assistant_text || data.error, data.tool_events, data.status);
      } catch (err) {
        appendMessage('agent', `Lỗi: ${err.message}`, null, 'error');
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

        // Set default comparison: first vs last
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
          <td style="color:var(--text-muted);">${c.what_it_tests || c.skill || ''}</td>
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
            <td><code>${r.changed_artifact}</code></td>
            <td style="color:var(--text-muted);">${r.hypothesis || ''}</td>
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
