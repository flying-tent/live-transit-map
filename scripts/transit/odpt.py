"""公共交通オープンデータセンター（ODPT）の列車運行情報 odpt:TrainInformation を読む。"""
from __future__ import annotations

import os
import urllib.parse

from .common import classify, find_section, hhmm, http_get_json, make_incident


def _ja(value) -> str:
    if isinstance(value, dict):
        return value.get("ja") or value.get("en") or ""
    return value or ""


def _expected(value) -> str | None:
    t = hhmm(value)
    return f"{t}頃" if t else None


def parse(items: list[dict], railways: dict, lines: dict, source_id: str) -> tuple[list[dict], list[str]]:
    """ODPT の配列を incident の配列にする。対応表にない路線IDは unmapped に入れて返す。"""
    incidents, unmapped = [], []
    for item in items:
        railway = item.get("odpt:railway")
        if not railway:
            continue  # 会社全体のお知らせ（路線が特定できない）は対象外
        target = railways.get(railway)
        if not target:
            if railway not in unmapped:
                unmapped.append(railway)
            continue
        map_id, line_id = target
        line = next((l for l in lines.get(map_id, {}).get("lines", []) if l["id"] == line_id), None)
        if not line:
            unmapped.append(f"{railway} → {map_id}/{line_id}（路線図にありません）")
            continue
        status_txt = _ja(item.get("odpt:trainInformationStatus"))
        text = _ja(item.get("odpt:trainInformationText"))
        status = classify(status_txt, text)
        if not status:
            continue
        detail = text or status_txt
        incidents.append(make_incident(
            map_id, line, status, detail,
            section=find_section(text, line["stations"]),
            since=hhmm(item.get("odpt:timeOfOrigin")),
            expected=_expected(item.get("odpt:resumeEstimate")),
            source=source_id,
        ))
    return incidents, unmapped


def fetch(config: dict, lines: dict, raw_dir: str | None = None) -> dict:
    """設定の各エンドポイントを読み、結果をまとめて返す。キーが未設定のエンドポイントは飛ばす。"""
    incidents, unmapped, used, errors = [], [], 0, []
    for ep in config["endpoints"]:
        key = os.environ.get(ep["key_env"], "").strip()
        if not key:
            continue
        used += 1
        url = ep["url"] + "?" + urllib.parse.urlencode({"acl:consumerKey": key})
        try:
            items = http_get_json(url)
        except Exception as e:  # noqa: BLE001  通信失敗は記録して続ける
            errors.append(f"{ep['name']}: {type(e).__name__}")
            continue
        if raw_dir:
            import json
            with open(os.path.join(raw_dir, f"odpt_{ep['id']}.json"), "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=1)
        inc, un = parse(items, config["railways"], lines, "odpt")
        incidents += inc
        unmapped += [u for u in un if u not in unmapped]
    return {"used": used, "incidents": incidents, "unmapped": unmapped, "errors": errors}
