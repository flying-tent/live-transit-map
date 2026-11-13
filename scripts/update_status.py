"""各社の運行情報を集めて docs/status.json を作る。

使い方:
  node scripts/export_lines.mjs > build/lines.json
  python scripts/update_status.py --lines build/lines.json --out docs/status.json

環境変数:
  ODPT_CONSUMER_KEY   ODPT（通常）のアクセストークン
  ODPT_CHALLENGE_KEY  ODPT（チャレンジ）のアクセストークン（任意）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from transit import jrwest, odpt  # noqa: E402
from transit.common import JST, http_get_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {
    # id: (表示名, モジュール, 設定ファイル)
    "odpt": ("首都圏（ODPT）", odpt, "odpt.json"),
    "jrwest": ("JR西日本", jrwest, "jrwest.json"),
}


def load_previous(url_or_path: str | None) -> dict:
    if not url_or_path:
        return {}
    try:
        if url_or_path.startswith("http"):
            return http_get_json(url_or_path)
        return json.loads(Path(url_or_path).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"前回の status.json を読めませんでした: {e}", file=sys.stderr)
        return {}


def dedupe(incidents: list[dict]) -> list[dict]:
    seen, out = set(), []
    for i in incidents:
        key = (i["map"], i["line"], i.get("from"), i.get("to"), i["status"])
        if key not in seen:
            seen.add(key)
            out.append(i)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", default=str(ROOT / "build/lines.json"))
    ap.add_argument("--out", default=str(ROOT / "docs/status.json"))
    ap.add_argument("--previous", help="前回の status.json（URL かパス）。取得に失敗した会社の分を引き継ぐ")
    ap.add_argument("--raw-dir", help="各社から受け取った生データを保存するフォルダ（調整用）")
    ap.add_argument("--only", nargs="*", help="指定した取得元だけ動かす（例: --only odpt）")
    args = ap.parse_args()

    lines = json.loads(Path(args.lines).read_text(encoding="utf-8"))
    if args.raw_dir:
        os.makedirs(args.raw_dir, exist_ok=True)
    previous = load_previous(args.previous)

    incidents, sources, coverage = [], [], []
    for sid, (name, module, cfg_file) in SOURCES.items():
        if args.only and sid not in args.only:
            continue
        cfg = json.loads((ROOT / "config" / cfg_file).read_text(encoding="utf-8"))
        try:
            res = module.fetch(cfg, lines, args.raw_dir)
        except Exception as e:  # noqa: BLE001  1社の失敗で全体を止めない
            res = {"used": 1, "incidents": [], "unmapped": [], "errors": [f"{type(e).__name__}: {e}"]}
        if not res["used"]:
            print(f"[{sid}] アクセストークン未設定のため飛ばしました")
            continue
        maps = cfg.get("maps") or list(cfg.get("areas", {}).values())
        coverage += [m for m in maps if m not in coverage]
        ok = not res["errors"]
        got = res["incidents"]
        if not ok and not got:
            # 全滅したときは前回の情報を引き継ぐ
            got = [i for i in previous.get("incidents", []) if i.get("source") == sid]
        incidents += got
        entry = {"id": sid, "name": name, "ok": ok, "count": len(got)}
        if res["errors"]:
            entry["errors"] = res["errors"]
        if res["unmapped"]:
            entry["unmapped"] = res["unmapped"]
        sources.append(entry)
        print(f"[{sid}] {'OK' if ok else 'NG'} 件数={len(got)} エラー={res['errors']} 未対応={len(res['unmapped'])}")
        for u in res["unmapped"]:
            print(f"    未対応: {u}")

    manual = json.loads((ROOT / "config/manual.json").read_text(encoding="utf-8"))
    incidents += manual.get("incidents", [])

    status = {
        "updatedAt": datetime.now(JST).isoformat(timespec="seconds"),
        "incidents": dedupe(incidents),
        "sources": sources,
        "coverage": coverage,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{args.out} に {len(status['incidents'])} 件を書き出しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
