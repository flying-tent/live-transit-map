"""路線図の線を45度単位（横・縦・斜め45度）にそろえる整形ツール。

  python tools/octilinear.py                 # shutoken-subway 以外のすべての地図
  python tools/octilinear.py kansai-jr ...   # 指定した地図だけ

やること:
  1. 座標の拡大（k）を座標に焼き込み、駅を格子に合わせる
  2. 駅間の線がなるべく45度単位の直線になるよう、駅を近くの格子点へ少しずつ動かす
  3. それでも直線にならない駅間は、曲がり1回（直線＋斜め）で結ぶ
docs/maps.js を書き換えます（元の座標は git の履歴で戻せます）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAPS_JS = ROOT / "docs" / "maps.js"
SKIP_DEFAULT = {"shutoken-subway"}  # 手で調整済み


def load_maps() -> dict:
    js = MAPS_JS.read_text(encoding="utf-8") + "\n;process.stdout.write(JSON.stringify(MAPS));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def is_oct(a, b) -> bool:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return dx == 0 or dy == 0 or abs(dx) == abs(dy)


def optimize(M: dict, grid: int, radius: int = 2, passes: int = 6) -> None:
    k = M.pop("k", 1)
    st = {n: [round(v[0] * k / grid) * grid, round(v[1] * k / grid) * grid] + v[2:] for n, v in M["st"].items()}
    for l in M["lines"]:
        l["nodes"] = [n for n in l["nodes"] if isinstance(n, str)]  # 曲がり角は作り直す
        l.pop("badge", None)
        l.pop("off", None)
    for f in ("center", "focus"):
        if M.get(f):
            M[f] = [M[f][0] * k, M[f][1] * k]
    if M.get("texts"):
        M["texts"] = [[x * k, y * k, t] for x, y, t in M["texts"]]
    for L in M.get("landmarks", []):
        if "pts" in L:
            L["pts"] = [[x * k, y * k] for x, y in L["pts"]]
        for f in ("x", "y"):
            if f in L:
                L[f] = L[f] * k

    nbrs = {n: set() for n in st}
    for l in M["lines"]:
        seq = l["nodes"] + ([l["nodes"][0]] if l.get("loop") else [])
        for a, b in zip(seq, seq[1:]):
            if a != b:
                nbrs[a].add(b)
                nbrs[b].add(a)
    orig = {n: v[:2] for n, v in st.items()}

    def cost(n, pos):
        c = 0.0
        for m in nbrs[n]:
            q = st[m][:2]
            if not is_oct(pos, q):
                c += 1
            # 駅の並び順（前後関係）が入れ替わらないように
            for i in (0, 1):
                o = orig[m][i] - orig[n][i]
                if abs(o) > grid and (q[i] - pos[i]) * o < 0:
                    c += 3
            if pos == q:
                c += 50
        c += 0.12 * (abs(pos[0] - orig[n][0]) + abs(pos[1] - orig[n][1])) / grid
        for m, p in st.items():
            if m == n:
                continue
            d_new = max(abs(p[0] - pos[0]), abs(p[1] - pos[1]))
            d_old = max(abs(orig[m][0] - orig[n][0]), abs(orig[m][1] - orig[n][1]))
            if d_new < min(d_old, 70) - 1:
                c += 10  # ほかの駅に近づきすぎる
        return c

    order = sorted(st, key=lambda n: len(nbrs[n]))  # 乗り換えの少ない駅から動かす
    for _ in range(passes):
        moved = False
        for n in order:
            x0, y0 = st[n][:2]
            best, bc = (x0, y0), cost(n, [x0, y0])
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    cand = [orig[n][0] + dx * grid, orig[n][1] + dy * grid]
                    c = cost(n, cand)
                    if c < bc - 1e-9:
                        best, bc = tuple(cand), c
            if list(best) != [x0, y0]:
                st[n][:2] = list(best)
                moved = True
        if not moved:
            break

    deg = {n: 0 for n in st}
    for l in M["lines"]:
        for n in l["nodes"]:
            deg[n] += 1

    def route(a, b):
        (x1, y1), (x2, y2) = st[a][:2], st[b][:2]
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 or dy == 0 or abs(dx) == abs(dy):
            return []
        sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
        m = min(abs(dx), abs(dy))
        # 乗り換えの多い駅の側を縦・横の直線にする（同点なら名前順で固定し、共有区間の形をそろえる）
        if (deg[a], a) > (deg[b], b):
            return [[x2 - sx * m, y2 - sy * m]]
        return [[x1 + sx * m, y1 + sy * m]]

    for l in M["lines"]:
        seq = l["nodes"]
        nodes = []
        for i, s in enumerate(seq):
            nodes.append(s)
            nxt = seq[i + 1] if i + 1 < len(seq) else (seq[0] if l.get("loop") else None)
            if nxt and nxt != s:
                nodes += route(s, nxt)
        l["nodes"] = nodes
    M["st"] = st


def dump(maps: dict) -> str:
    J = lambda v: json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    out = ["// 路線図データ。線は45度単位（tools/octilinear.py で整形）", "const MAPS={};", ""]
    for mid, M in maps.items():
        out.append(f"// ---------------- {M['title']} ----------------")
        out.append(f"MAPS['{mid}']={{")
        for key, val in M.items():
            if key in ("st", "lines"):
                continue
            out.append(f"  {key}:{J(val)},")
        out.append("  st:{")
        out += [f"    '{n}':{J(v)}," for n, v in M["st"].items()]
        out.append("  },")
        out.append("  lines:[")
        for l in M["lines"]:
            nodes = l["nodes"]
            rest = {k: v for k, v in l.items() if k != "nodes"}
            out.append("    {" + ",".join(f"{k}:{J(v)}" for k, v in rest.items()) + f",nodes:{J(nodes)}}},")
        out.append("  ],")
        out.append("};")
        out.append("")
    return "\n".join(out)


def main():
    maps = load_maps()
    targets = sys.argv[1:] or [m for m in maps if m not in SKIP_DEFAULT]
    for mid in targets:
        M = maps[mid]
        grid = M.pop("grid", 20)
        optimize(M, grid)
        M["grid"] = grid
        bent = sum(1 for l in M["lines"] for n in l["nodes"] if not isinstance(n, str))
        print(f"{mid}: 曲がり角 {bent} か所")
    MAPS_JS.write_text(dump(maps), encoding="utf-8")


if __name__ == "__main__":
    main()
