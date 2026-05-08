from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Set


DEFAULT_MEMORY: Dict[str, object] = {
    "stack": [],
    "constraints": [],
    "decisions": [],
    "notes": "",
}


@dataclass
class MemoryStore:
    path: str
    default_memory: Dict[str, object] = field(
        default_factory=lambda: dict(DEFAULT_MEMORY)
    )

    def _summarize_text_budget(self, text: str, max_chars: int) -> str:
        t = (text or "").strip()
        if len(t) <= max_chars:
            return t
        keep = max(120, max_chars - 40)
        head = t[: keep // 2].rstrip()
        tail = t[-(keep - len(head)) :].lstrip()
        return f"{head}\n...[memory summarized]...\n{tail}"

    def prune(self, mem: Dict[str, object]) -> Dict[str, object]:
        max_items = max(3, int(os.environ.get("CLOGEM_MEMORY_MAX_ITEMS", "30")))
        max_notes = max(
            400, int(os.environ.get("CLOGEM_MEMORY_MAX_NOTES_CHARS", "3000"))
        )

        out = dict(self.default_memory)
        out.update(mem or {})
        for key in ("stack", "constraints"):
            vals = out.get(key)
            if not isinstance(vals, list):
                out[key] = []
                continue
            clean = [str(x).strip() for x in vals if str(x).strip()]
            dedup: List[str] = []
            seen: Set[str] = set()
            for item in clean:
                k = item.lower()
                if k in seen:
                    continue
                seen.add(k)
                dedup.append(item)
            out[key] = dedup[-max_items:]

        decisions = out.get("decisions")
        if not isinstance(decisions, list):
            out["decisions"] = []
        else:
            normalized = []
            for d in decisions:
                if isinstance(d, dict) and str(d.get("text", "")).strip():
                    normalized.append(
                        {
                            "text": str(d.get("text", "")).strip(),
                            "date": str(d.get("date", "")).strip(),
                        }
                    )
                elif str(d).strip():
                    normalized.append({"text": str(d).strip(), "date": ""})
            out["decisions"] = normalized[-max_items:]

        out["notes"] = self._summarize_text_budget(str(out.get("notes", "")), max_notes)
        return out

    def load(self) -> Dict[str, object]:
        if not os.path.isfile(self.path):
            self.save(dict(self.default_memory))
            return dict(self.default_memory)
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return dict(self.default_memory)
        out = dict(self.default_memory)
        if isinstance(data, dict):
            for k in self.default_memory:
                if k in data:
                    out[k] = data[k]
        return out

    def save(self, data: Dict[str, object]) -> None:
        payload = self.prune(
            data if isinstance(data, dict) else dict(self.default_memory)
        )
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def format_for_prompt(self, mem: Dict[str, object]) -> str:
        lines: List[str] = []
        stack = mem.get("stack") or []
        constraints = mem.get("constraints") or []
        decisions = mem.get("decisions") or []
        notes = (mem.get("notes") or "").strip()

        if isinstance(stack, list) and stack:
            lines.append("Stack / tools (prefer these unless the task requires otherwise):")
            for s in stack:
                if str(s).strip():
                    lines.append(f"  - {str(s).strip()}")
            lines.append(
                "If the current task names a different programming language, framework, or stack "
                "(or explicitly switches away from the items above), follow the task for this deliverable."
            )
        if isinstance(constraints, list) and constraints:
            lines.append("Constraints / rules:")
            for c in constraints:
                if str(c).strip():
                    lines.append(f"  - {str(c).strip()}")
        if isinstance(decisions, list) and decisions:
            lines.append("Past decisions (honor unless the user clearly overrides):")
            for d in decisions:
                if isinstance(d, dict) and d.get("text"):
                    t = str(d["text"]).strip()
                    when = str(d.get("date", "")).strip()
                    lines.append(f"  - [{when}] {t}" if when else f"  - {t}")
                elif str(d).strip():
                    lines.append(f"  - {str(d).strip()}")
        if notes:
            lines.append("Additional notes:")
            for part in notes.splitlines():
                if part.strip():
                    lines.append(f"  {part.strip()}")

        if not lines:
            return ""
        return "## Persistent memory (from memory.json)\n" + "\n".join(lines) + "\n\n---\n\n"
