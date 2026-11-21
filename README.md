# live-transit-map

全国の鉄道の運行状況を路線図の上に表示するページです。運転見合わせの区間は赤く点滅し、遅延の区間は黄色く光ります。
運行情報は GitHub Actions が10分ごとに集め、GitHub Pages で公開します。費用はかかりません（公開リポジトリの場合）。

```
GitHub Actions（10分ごと）
  ├─ node scripts/export_lines.mjs     … 路線図（docs/maps.js）から路線・駅の一覧を作る
  ├─ python scripts/update_status.py   … 各社の運行情報を集め、docs/status.json を作る
  └─ GitHub Pages に docs/ を公開        … ページは status.json を2分ごとに読み直す
```

## 最初の設定

1. **GitHub Pages を有効にする**
   リポジトリの Settings → Pages → Build and deployment の Source を「GitHub Actions」にします。
2. **ODPT のアクセストークンを登録する（首都圏の自動更新に必要）**
   公共交通オープンデータセンター（https://developer.odpt.org/ ）で開発者登録をして、アクセストークンを取得します。
   Settings → Secrets and variables → Actions → New repository secret で、次の名前で登録します。
   - `ODPT_CONSUMER_KEY` … 通常の API のトークン
   - `ODPT_CHALLENGE_KEY` … チャレンジ用 API のトークン（持っている場合だけ）
3. **動作を確認する**
   Actions タブ →「運行情報の更新と公開」→ Run workflow で、`save_raw` にチェックを入れて実行します。
   実行ログに、取得元ごとの件数と「未対応」の路線が出ます。保存された生データ（raw-data）は、対応表の調整に使えます。
4. 公開先は `https://<ユーザー名>.github.io/live-transit-map/` です。

## 自動更新の対象

| 取得元 | 対象の路線図 | 方式 | 状態 |
|---|---|---|---|
| ODPT（公共交通オープンデータセンター） | 首都圏 地下鉄（東京メトロ・都営） | 公式のオープンデータ API | 稼働中。通常のトークンで届くのは東京メトロ・都営など。JR東日本・私鉄は対応表だけ用意済み（データが届けば自動で対象になります） |
| JR西日本 列車走行位置サイト | 関西 JR・中国 JR | 公式サイトが使っている JSON（**非公式**） | 試験的。形式が変わると取得できなくなります |

それ以外の路線図（新幹線、東海、北海道、東北、九州、関西・中国の私鉄と地下鉄など）は、まだ自動更新の対象外です。
ページ上では「この路線図は自動更新の対象外です」と表示します。手動で情報を載せたいときは `config/manual.json` に書きます。

取得に失敗した会社があると、ページ上部に「一部の情報を取得できませんでした」と表示し、前回取得した情報を引き継ぎます。

## 対応表の調整

各社の路線と、路線図の路線（`docs/maps.js` の `lines` の `id`）の対応は `config/` にあります。

- `config/odpt.json` の `railways` … ODPT の `odpt:railway` の値 → `[地図ID, 路線ID]`
- `config/jrwest.json` の `lines` … JR西日本側の路線コード → 路線ID（対応表にない場合は路線名の一致で探します）

実行ログに「未対応」と出た路線は、ここに追加してください。追加したら `python -m unittest discover -s tests` で、対応先の路線が路線図にあるかを確認できます。

区間（「品川駅～池袋駅間」など）は運行情報の文章から読み取り、路線図に載っている駅どうしの場合だけ区間として表示します。読み取れないときは路線全体を表示します。

## 路線図の線の形

路線図の線は、横・縦・斜め45度の4方向だけで描きます。駅の位置を変えたり路線を足したりしたら、次のコマンドで整えます。

```sh
python tools/octilinear.py              # 首都圏の地下鉄（手で調整済み）以外のすべて
python tools/octilinear.py kansai-jr    # 指定した路線図だけ
```

駅を近くの格子点に少しずつ動かして、なるべく曲がらずにつながるようにします。それでも直線にならない駅間は、1回だけ曲げて結びます。

## 手元で動かす

```sh
mkdir -p build
node scripts/export_lines.mjs > build/lines.json
ODPT_CONSUMER_KEY=xxxx python scripts/update_status.py --out docs/status.json --raw-dir build/raw
python -m http.server -d docs 8000   # http://localhost:8000/ で確認
python -m unittest discover -s tests
```

## status.json の書式

```json
{
  "updatedAt": "2026-11-14T08:40:00+09:00",
  "incidents": [
    {"map": "shutoken-jr", "line": "yamanote", "from": "品川", "to": "池袋",
     "status": "suspend", "detail": "…", "since": "08:12", "expected": "09:30頃", "source": "odpt"}
  ],
  "sources": [{"id": "odpt", "name": "首都圏（ODPT）", "ok": true, "count": 1}],
  "coverage": ["shutoken-jr", "shutoken-subway", "shutoken-private", "kansai-jr", "chugoku-jr"]
}
```

- `status` … `suspend`（運転見合わせ・赤点滅）/ `delay`（遅延・黄色点灯）/ `offhours`（運行時間外・光らせない）
- 日本時間 1:00〜4:30 は、全路線を「運行時間外」として表示します
- `from` / `to` を省くと路線全体
- 地図ID … `shinkansen` または `{地域}-{種別}`（地域 = hokkaido / tohoku / shutoken / tokai / kansai / chugoku / kyushu、種別 = jr / subway / private）

## 注意

- 各社のサイトやデータの利用条件を守ってください。ODPT のデータは、ODPT の利用規約に従って表示してください。
- JR西日本のデータは公開 API ではありません。アクセス間隔を短くしすぎないでください（既定は10分ごと）。
- GitHub Actions の定期実行は、混雑時に数分〜数十分遅れることがあります。
- 60日間リポジトリに動きがないと定期実行が止まるため、`keepalive.yml` が月1回空のコミットを入れます。
