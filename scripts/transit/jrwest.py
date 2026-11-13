"""JR西日本「列車走行位置」サイトが使っている運行情報 JSON を読む。

注意: JR西日本が公開しているオープンデータではなく、公式サイトの画面が内部で使っている非公式の JSON です。
形式が予告なく変わる可能性があるため、中身の構造に頼りすぎない読み方をしています。
"""
from __future__ import annotations

import json
import os

from .common import classify, find_section, hhmm, http_get_json, make_incident, section_from_names


def _strings(obj) -> list[str]:
    """入れ子の dict / list から文字列をすべて取り出す。"""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _strings(v)]
    return []


def _pick(info: dict, *keys: str):
    for k in keys:
        v = info.get(k)
        if v:
            return v
    return None


def _match_line(code: str, info: dict, map_lines: list[dict], code_map: dict) -> dict | None:
    line_id = code_map.get(code)
    if line_id:
        return next((l for l in map_lines if l["id"] == line_id), None)
    # 対応表にない路線は、データ中の文字列に路線名が含まれているかで探す（長い名前を優先）
    text = " ".join(_strings(info))
    for line in sorted(map_lines, key=lambda l: -len(l["name"])):
        if line["name"] in text:
            return line
    return None


def parse(data: dict, map_id: str, lines: dict, code_map: dict) -> tuple[list[dict], list[str]]:
    incidents, unmapped = [], []
    map_lines = lines.get(map_id, {}).get("lines", [])
    for code, info in (data.get("lines") or {}).items():
        if not isinstance(info, dict):
            continue
        line = _match_line(code, info, map_lines, code_map)
        if not line:
            unmapped.append(f"{map_id}:{code}")
            continue
        texts = _strings(info)
        status = classify(*texts)
        if not status:
            continue
        cause = _pick(info, "cause", "reason")
        detail = " ".join(t for t in (_pick(info, "status", "statusText"), cause, _pick(info, "text", "message", "detail")) if t) \
            or " ".join(texts)
        sec = info.get("section") if isinstance(info.get("section"), dict) else {}
        section = section_from_names(sec.get("from"), sec.get("to"), line["stations"]) \
            or find_section(" ".join(texts), line["stations"])
        incidents.append(make_incident(
            map_id, line, status, detail, section=section,
            since=hhmm(_pick(info, "occurrenceTime", "time", "updateTime")),
            expected=_pick(info, "resumeTime", "expectedResumption"),
            source="jrwest",
        ))
    return incidents, unmapped


def fetch(config: dict, lines: dict, raw_dir: str | None = None) -> dict:
    incidents, unmapped, errors = [], [], []
    for area, map_id in config["areas"].items():
        url = config["base"] + f"area_{area}_trafficinfo.json"
        try:
            data = http_get_json(url)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{area}: {type(e).__name__}")
            continue
        if raw_dir:
            with open(os.path.join(raw_dir, f"jrwest_{area}.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        inc, un = parse(data, map_id, lines, config.get("lines", {}).get(map_id, {}))
        incidents += inc
        unmapped += un
    return {"used": len(config["areas"]), "incidents": incidents, "unmapped": unmapped, "errors": errors}
