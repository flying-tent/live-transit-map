import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from transit import jrwest, odpt  # noqa: E402
from transit.common import classify, find_section  # noqa: E402

LINES = json.loads((ROOT / "build/lines.json").read_text(encoding="utf-8"))
FIX = ROOT / "tests/fixtures"


class CommonTest(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify("運転見合わせ"), "suspend")
        self.assertEqual(classify("一部列車に遅れが出ています"), "delay")
        self.assertIsNone(classify("現在、平常どおり運転しています。"))
        self.assertIsNone(classify(""))
        self.assertIsNone(classify("現在、１５分以上の遅延はありません。"))
        self.assertEqual(classify("本日の運転は終了しました。"), "offhours")
        self.assertEqual(classify("本日の運転は終了しました。運転見合わせ中の区間があります"), "suspend")
        self.assertEqual(classify("遅延はありません。一部列車に遅れが出ています"), "delay")

    def test_section(self):
        st = ["東京", "新橋", "品川", "大崎", "渋谷", "新宿", "池袋"]
        self.assertEqual(find_section("品川駅～池袋駅間で運転を見合わせ", st), ("品川", "池袋"))
        self.assertEqual(find_section("新宿〜渋谷間", st), ("新宿", "渋谷"))
        self.assertIsNone(find_section("全線で遅れ", st))


class OdptTest(unittest.TestCase):
    def test_parse(self):
        cfg = json.loads((ROOT / "config/odpt.json").read_text(encoding="utf-8"))
        items = json.loads((FIX / "odpt_sample.json").read_text(encoding="utf-8"))
        inc, unmapped = odpt.parse(items, cfg["railways"], LINES, "odpt")
        self.assertEqual(len(inc), 2)
        y = inc[0]
        self.assertEqual((y["map"], y["line"], y["status"]), ("shutoken-jr", "yamanote", "suspend"))
        self.assertEqual((y["from"], y["to"], y["since"], y["expected"]), ("品川", "池袋", "08:12", "09:30頃"))
        self.assertEqual(inc[1]["line"], "oedo")
        self.assertEqual(unmapped, ["odpt.Railway:Foo.Bar"])

    def test_config_targets_exist(self):
        cfg = json.loads((ROOT / "config/odpt.json").read_text(encoding="utf-8"))
        for rid, (m, l) in cfg["railways"].items():
            self.assertIn(l, [x["id"] for x in LINES[m]["lines"]], rid)


class JrWestTest(unittest.TestCase):
    def test_parse(self):
        cfg = json.loads((ROOT / "config/jrwest.json").read_text(encoding="utf-8"))
        data = json.loads((FIX / "jrwest_kinki.json").read_text(encoding="utf-8"))
        inc, unmapped = jrwest.parse(data, "kansai-jr", LINES, cfg["lines"]["kansai-jr"])
        by = {i["line"]: i for i in inc}
        self.assertEqual(by["loop"]["status"], "suspend")
        self.assertNotIn("from", by["loop"])
        self.assertEqual((by["hanwa"]["from"], by["hanwa"]["to"]), ("天王寺", "和歌山"))
        self.assertEqual((by["kyoto"]["from"], by["kyoto"]["to"]), ("京都", "大阪"))
        self.assertEqual(unmapped, [])

    def test_config_targets_exist(self):
        cfg = json.loads((ROOT / "config/jrwest.json").read_text(encoding="utf-8"))
        for m, codes in cfg["lines"].items():
            ids = [x["id"] for x in LINES[m]["lines"]]
            for code, l in codes.items():
                self.assertIn(l, ids, f"{m}:{code}")


if __name__ == "__main__":
    unittest.main()
