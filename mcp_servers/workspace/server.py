"""Workspace MCP server (A3): calendar availability, tentative interview holds, email drafts.

Backed by a documented local mock (JSON file under data/processed/workspace/). Swapping in Google
Calendar / Gmail means re-implementing `LocalWorkspace` with their official APIs; the tool
contracts below stay the same, so agents are unaffected.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from mcp_servers.common import DATA_DIR, AuditLog


class Slot(BaseModel):
    start: str
    end: str


class SlotList(BaseModel):
    timezone: str
    slots: list[Slot]


class Hold(BaseModel):
    hold_id: str
    start: str
    end: str
    title: str
    status: str = "tentative"


class EmailDraft(BaseModel):
    draft_id: str
    to: str
    subject: str
    body: str
    status: str = "draft"


class LocalWorkspace:
    def __init__(self, path: Path, tz: str = "Asia/Karachi", work_hours=(10, 18)):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tz = tz
        self.work_hours = work_hours
        self.state = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"busy": [], "holds": [], "drafts": []}

    def _save(self):
        self.path.write_text(json.dumps(self.state, indent=1), encoding="utf-8")

    def free_slots(self, days: int, duration_min: int, now: datetime | None = None) -> list[Slot]:
        tz = ZoneInfo(self.tz)
        now = (now or datetime.now(timezone.utc)).astimezone(tz)
        taken = [(datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
                 for b in self.state["busy"] + self.state["holds"]]
        out = []
        day = now.date()
        for d in range(1, days + 1):
            date = day + timedelta(days=d)
            if date.weekday() >= 5:
                continue
            for hour in range(self.work_hours[0], self.work_hours[1]):
                start = datetime(date.year, date.month, date.day, hour, tzinfo=tz)
                end = start + timedelta(minutes=duration_min)
                if end.hour > self.work_hours[1] or any(s < end and start < e for s, e in taken):
                    continue
                out.append(Slot(start=start.isoformat(), end=end.isoformat()))
                break  # one slot per day keeps the offer short
        return out

    def hold(self, start: str, duration_min: int, title: str) -> Hold:
        s = datetime.fromisoformat(start)
        e = s + timedelta(minutes=duration_min)
        for h in self.state["holds"] + self.state["busy"]:
            if datetime.fromisoformat(h["start"]) < e and s < datetime.fromisoformat(h["end"]):
                raise ToolError("ERROR: slot no longer free")
        h = Hold(hold_id="H-" + uuid.uuid4().hex[:8], start=s.isoformat(), end=e.isoformat(), title=title)
        self.state["holds"].append(h.model_dump())
        self._save()
        return h

    def draft(self, to: str, subject: str, body: str) -> EmailDraft:
        d = EmailDraft(draft_id="D-" + uuid.uuid4().hex[:8], to=to, subject=subject, body=body)
        self.state["drafts"].append(d.model_dump())
        self._save()
        return d


def build_server(data_dir: Path | None = None, tz: str | None = None) -> FastMCP:
    data_dir = Path(data_dir or DATA_DIR)
    ws = LocalWorkspace(data_dir / "workspace" / "calendar.json", tz or os.environ.get("WORKSPACE_TZ", "Asia/Karachi"))
    audit = AuditLog(data_dir / "audit" / "workspace.jsonl")
    mcp = FastMCP("gigbid-workspace", instructions="Calendar availability, tentative interview holds and email drafts.")
    mcp.workspace = ws

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
              description="Free interview slots on weekdays within working hours, at most one per day.")
    def free_slots(days: Annotated[int, Field(ge=1, le=14)] = 5,
                   duration_min: Annotated[int, Field(ge=15, le=120)] = 30) -> SlotList:
        res = SlotList(timezone=ws.tz, slots=ws.free_slots(days, duration_min)[:3])
        audit.write(user_id="local", tool="free_slots", args={"days": days}, result=res.model_dump(), trace_id=None)
        return res

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
              description="Create a TENTATIVE calendar hold for an interview slot (not an invitation).")
    def create_interview_hold(start: Annotated[str, Field(description="ISO-8601 start with offset")],
                              title: Annotated[str, Field(min_length=3, max_length=120)],
                              duration_min: Annotated[int, Field(ge=15, le=120)] = 30) -> Hold:
        h = ws.hold(start, duration_min, title)
        audit.write(user_id="local", tool="create_interview_hold", args={"start": start, "title": title},
                    result=h.model_dump(), trace_id=None)
        return h

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
              description="Create an email DRAFT (never sends).")
    def create_email_draft(to: Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")],
                           subject: Annotated[str, Field(min_length=1, max_length=200)],
                           body: Annotated[str, Field(min_length=1, max_length=5000)]) -> EmailDraft:
        d = ws.draft(to, subject, body)
        audit.write(user_id="local", tool="create_email_draft", args={"to": to, "subject": subject},
                    result={"draft_id": d.draft_id}, trace_id=None)
        return d

    return mcp


if __name__ == "__main__":
    from mcp_servers.common import run_server

    run_server(build_server(), int(os.environ.get("MCP_PORT", 8103)))
