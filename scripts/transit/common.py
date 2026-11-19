"""各社のデータを、路線図用の共通形式（incident）にそろえるための道具。"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
USER_AGENT = "live-transit-map (+https://github.com/k-shunnosuke/live-transit-map)"


def http_get_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


# ---------------------------------------------------------------- 状態の判定
SUSPEND_WORDS = ("運転見合わせ", "運転を見合わせ", "見合わせて", "運休", "運転を休止", "不通")
DELAY_WORDS = ("遅れ", "遅延", "ダイヤが乱れ", "ダイヤ乱れ", "運転再開", "一部列車", "直通運転を中止", "折り返し運転")
NORMAL_WORDS = ("平常どおり", "平常通り", "平常運転", "通常どおり")
NEGATION_RE = re.compile(r"(遅延|遅れ|運転見合わせ|見合わせ|運休)(は|も|が)?(ありません|ございません|なし|発生していません|出ていません)")


def classify(*texts: str | None) -> str | None:
    """文章から 'suspend' / 'delay' / None（平常）を判定する。"""
    text = " ".join(t for t in texts if t)
    if not text.strip():
        return None
    # 「15分以上の遅延はありません」のような否定は平常として扱う
    if NEGATION_RE.search(text) and not any(w in NEGATION_RE.sub("", text) for w in SUSPEND_WORDS + DELAY_WORDS):
        return None
    if any(w in text for w in SUSPEND_WORDS):
        return "suspend"
    if any(w in text for w in DELAY_WORDS):
        return "delay"
    if any(w in text for w in NORMAL_WORDS):
        return None
    # 判定できない文章は「遅れている区間など」として扱う（見落とすよりは表示する）
    return "delay"


# ---------------------------------------------------------------- 区間の読み取り
_SEP = r"(?:～|〜|~|－|−|-|から)"
_NAME = r"([^\s、。・（）()「」\[\]～〜~－−\-]{1,12}?)"
SECTION_RE = re.compile(_NAME + r"駅?" + _SEP + _NAME + r"駅?(?:間|の間)")


def _norm(name: str) -> str:
    return name.replace("駅", "").replace("ヶ", "ケ").replace("ヵ", "ケ").strip()


def find_section(text: str | None, stations: list[str]) -> tuple[str, str] | None:
    """文章中の「A～B間」から、この路線図に載っている駅の組を探す。"""
    if not text:
        return None
    lookup = {_norm(s): s for s in stations}
    for m in SECTION_RE.finditer(text):
        a, b = _norm(m.group(1)), _norm(m.group(2))
        # 「東京駅～大宮」のように前に余計な語が付いている場合に備え、末尾一致も試す
        sa = lookup.get(a) or next((v for k, v in lookup.items() if a.endswith(k)), None)
        sb = lookup.get(b) or next((v for k, v in lookup.items() if b.endswith(k)), None)
        if sa and sb and sa != sb:
            return sa, sb
    return None


def section_from_names(a: str | None, b: str | None, stations: list[str]) -> tuple[str, str] | None:
    """データ側に駅名が入っているとき用。"""
    if not a or not b:
        return None
    lookup = {_norm(s): s for s in stations}
    sa, sb = lookup.get(_norm(a)), lookup.get(_norm(b))
    return (sa, sb) if sa and sb and sa != sb else None


# ---------------------------------------------------------------- 時刻
def hhmm(value: str | None) -> str | None:
    """ISO 8601 の日時や「8時12分」を 'HH:MM' にする。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(JST)
        return dt.strftime("%H:%M")
    except ValueError:
        m = re.search(r"(\d{1,2})[:時](\d{2})", value)
        return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def make_incident(map_id: str, line: dict, status: str, detail: str, *,
                  section: tuple[str, str] | None = None, since: str | None = None,
                  expected: str | None = None, source: str = "") -> dict:
    inc = {"map": map_id, "line": line["id"], "status": status, "detail": (detail or "").strip()}
    if section:
        inc["from"], inc["to"] = section
    if since:
        inc["since"] = since
    if expected:
        inc["expected"] = expected
    if source:
        inc["source"] = source
    return inc
