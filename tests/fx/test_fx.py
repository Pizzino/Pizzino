"""Pruebas sin red de las skills fx-*, sobre respuestas reales de Yahoo y ForexFactory
guardadas el 2026-11-15 (tests/fx/fixtures).   python3 -m unittest discover -s tests/fx -v
"""
import argparse
import datetime
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SK = os.path.join(ROOT, ".claude", "skills")
FIX = os.path.join(ROOT, "tests", "fx", "fixtures")
CAL = os.path.join(FIX, "ff_calendar_2026-11-15.json")
sys.path.insert(0, os.path.join(SK, "fx-common"))
import fxlib as fx  # noqa: E402


def load(folder, name):
    spec = importlib.util.spec_from_file_location("fx_" + name, os.path.join(SK, folder, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


scan = load("fx-scanner", "scan")
econ = load("fx-calendar", "econ")
fxexit = load("fx-exit", "exit")
tm = load("fx-timemachine", "timemachine")
size = load("fx-budget", "size")
check = load("fx-risk", "check")
ticket = load("fx-ticket", "ticket")


def ns(**kw):
    base = dict(dir=None, now=None, offline=FIX, json=False, pairs=None, mine=False, no_write=True,
                pair=None, side=None, entry=None, stop="range-mid", target="2R", flat_by=None,
                replays=10000, seed=19, window=2)
    base.update(kw)
    return argparse.Namespace(**base)


def dt(s):
    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M")


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cfg = fx.load_config(ns(dir=self.dir))

    def tearDown(self):
        shutil.rmtree(self.dir)

    def entry(self, now="2026-11-13 09:30"):
        row, _ = scan.scan_session("EURUSD", "ny", self.cfg, ns(now=now, dir=self.dir))
        row["setup"] = "session"
        fx.write_json(os.path.join(self.dir, "entry.json"), row)
        return row

    def plan(self, **kw):
        self.entry()
        p = fxexit.build_plan(ns(dir=self.dir, **kw), self.cfg)
        fx.write_json(os.path.join(self.dir, "plan.json"), p)
        return p

    def order(self):
        p = self.plan()
        return size.size(p, self.cfg, 1.0, p["entry"])


class TestLib(Base):
    def test_pairs_and_pips(self):
        self.assertEqual(len(fx.PAIRS), 28)
        for p in fx.MAJORS + ["EURGBP", "GBPJPY", "AUDNZD", "CHFJPY"]:
            self.assertIn(p, fx.PAIRS)
        self.assertEqual(fx.norm_pair("eur/usd"), "EURUSD")
        self.assertEqual(fx.norm_pair("USDJPY=X"), "USDJPY")
        with self.assertRaises(fx.FxError):
            fx.norm_pair("USDEUR")
        with self.assertRaises(fx.FxError):
            fx.norm_pair("TSLA")
        self.assertEqual(fx.pip("USDJPY"), 0.01)
        self.assertEqual(fx.pip("EURUSD"), 0.0001)
        self.assertEqual(fx.to_pips("EURUSD", 0.00105), 10.5)
        self.assertEqual(fx.fmt("USDJPY", 159.8754), "159.875")

    def test_clocks(self):
        self.assertEqual(fx.ny_offset(dt("2026-07-01 12:00")), -4)
        self.assertEqual(fx.ny_offset(dt("2026-11-13 12:00")), -5)
        self.assertEqual(fx.ny_offset(dt("2026-11-01 05:59")), -4)   # el cambio es a las 06:00 UTC
        self.assertEqual(fx.ny_offset(dt("2026-11-01 06:00")), -5)
        self.assertEqual(fx.london_offset(dt("2026-07-01 12:00")), 1)
        self.assertEqual(fx.london_offset(dt("2026-10-25 01:00")), 0)
        self.assertEqual(fx.london_offset(dt("2026-03-29 01:00")), 1)
        # tres semanas de marzo en que EE.UU. ya cambio y Londres no
        self.assertEqual((fx.ny_offset(dt("2026-03-20 12:00")), fx.london_offset(dt("2026-03-20 12:00"))), (-4, 0))
        self.assertEqual(fx.local_to_utc(dt("2026-11-13 09:30"), "ny"), dt("2026-11-13 14:30"))
        self.assertEqual(fx.parse_now("2026-07-01 09:30"), dt("2026-07-01 13:30"))

    def test_week(self):
        self.assertTrue(fx.market_open(fx.parse_now("2026-11-13 16:59")))    # viernes
        self.assertFalse(fx.market_open(fx.parse_now("2026-11-13 17:00")))
        self.assertFalse(fx.market_open(fx.parse_now("2026-11-14 12:00")))   # sabado
        self.assertFalse(fx.market_open(fx.parse_now("2026-11-15 16:59")))   # domingo
        self.assertTrue(fx.market_open(fx.parse_now("2026-11-15 17:00")))
        self.assertFalse(fx.market_open(fx.parse_now("2026-12-25 10:00")))
        self.assertEqual(fx.fx_day(fx.parse_now("2026-11-15 18:00")).isoformat(), "2026-11-16")
        self.assertEqual(fx.fx_day(fx.parse_now("2026-11-13 16:00")).isoformat(), "2026-11-13")

    def test_session_window(self):
        rs, re_, eu = fx.session_window("london", datetime.date(2026, 11, 13))
        self.assertEqual((rs, re_, eu), (dt("2026-11-13 00:00"), dt("2026-11-13 08:00"), dt("2026-11-13 11:00")))
        rs, re_, eu = fx.session_window("london", datetime.date(2026, 7, 1))
        self.assertEqual(re_, dt("2026-07-01 07:00"))                        # verano: 08:00 Londres = 07:00 UTC
        rs, re_, eu = fx.session_window("ny", datetime.date(2026, 11, 13))
        self.assertEqual((rs, re_, eu), (dt("2026-11-13 13:00"), dt("2026-11-13 14:00"), dt("2026-11-13 17:00")))

    def test_indicators_and_rate(self):
        self.assertEqual(fx.rsi([1.0 + i * 0.01 for i in range(30)]), 100.0)
        self.assertIsNone(fx.rsi([1, 2, 3]))
        prices = {"EURUSD": 1.10, "USDJPY": 160.0, "GBPUSD": 1.32}
        self.assertEqual(fx.rate("USD", "USD", prices.get), 1.0)
        self.assertAlmostEqual(fx.rate("JPY", "USD", prices.get), 1 / 160.0)
        self.assertAlmostEqual(fx.rate("GBP", "USD", prices.get), 1.32)

    def test_bars_are_clean(self):
        res = fx.load_chart("EURUSD", "60d", "5m", FIX)
        bars = fx.bars_from(res, fx.data_time(res), "5m")
        self.assertTrue(all(b["t"] % 300 == 0 and fx.market_open(fx.utc_of(b["t"])) for b in bars))
        self.assertTrue(all(b["l"] <= min(b["o"], b["c"]) and b["h"] >= max(b["o"], b["c"]) for b in bars))
        cut = fx.bars_from(res, fx.parse_now("2026-11-13 09:22"), "5m")
        self.assertEqual(cut[-1]["t"], fx.ts_of(fx.parse_now("2026-11-13 09:15")))   # la de 09:20 sigue abierta


class TestScannerEntry(Base):
    def test_daily(self):
        res = fx.load_chart("EURUSD", "6mo", "1d", FIX)
        closes = [b["c"] for b in fx.bars_from(res, fx.data_time(res), "1d")]
        self.assertEqual(scan.daily_setups(closes), ["ruptura_20d_bajista"])
        res = fx.load_chart("USDJPY", "6mo", "1d", FIX)
        closes = [b["c"] for b in fx.bars_from(res, fx.data_time(res), "1d")]
        self.assertEqual(scan.daily_setups(closes), ["ruptura_20d_alcista"])
        self.assertEqual(scan.daily_setups([1.0] * 10), [])

    def test_ny_session(self):
        r = self.entry("2026-11-13 09:20")
        self.assertEqual(r["status"], "esperando")
        r = self.entry("2026-11-13 09:30")
        self.assertEqual((r["status"], r["side"], r["price"], r["entry_time"]), ("activada", "sell", 1.10509, "09:25"))
        self.assertEqual((r["range_high"], r["range_low"], r["range_pips"]), (1.10705, 1.10522, 18.4))

    def test_london_session(self):
        r, _ = scan.scan_session("GBPUSD", "london", self.cfg, ns(now="2026-11-13 10:30"))
        self.assertEqual((r["status"], r["side"], r["price"], r["entry_time"]), ("activada", "buy", 1.32424, "08:20"))
        r, _ = scan.scan_session("EURUSD", "london", self.cfg, ns(now="2026-11-13 10:30"))
        self.assertEqual(r["status"], "vencida")
        r, _ = scan.scan_session("EURUSD", "london", self.cfg, ns(now="2026-11-13 02:00"))
        self.assertEqual(r["status"], "esperando")

    def test_weekend(self):
        r, _ = scan.scan_session("EURUSD", "ny", self.cfg, ns(now="2026-11-14 10:00"))
        self.assertEqual(r["status"], "sin-datos")

    def test_wick_is_not_a_break(self):
        rng = {"high": 1.1000, "low": 1.0950}
        bars = [{"t": 600, "o": 1.0990, "h": 1.1010, "l": 1.0985, "c": 1.0995},
                {"t": 900, "o": 1.0995, "h": 1.1012, "l": 1.0990, "c": 1.1004}]
        br = fx.find_break(bars, rng, fx.utc_of(600), fx.utc_of(3000))
        self.assertEqual((br["side"], br["bar_t"], br["close_t"]), ("buy", 900, 1200))


class TestExit(Base):
    def test_default_plan(self):
        p = self.plan()
        self.assertEqual((p["stop"], p["target"], p["stop_pips"], p["target_r"]), (1.10614, 1.10299, 10.5, 2.0))
        self.assertEqual((p["net_risk_pips"], p["net_target_pips"], p["net_r"], p["flat_by"]), (11.5, 20.0, 1.74, "16:30"))

    def test_rules(self):
        self.assertEqual(self.plan(stop="range-far")["stop"], 1.10705)
        p = self.plan(stop="pips:15", target="1.5R")
        self.assertEqual((p["stop"], p["target"]), (1.10659, 1.10284))
        p = self.plan(stop="atr:0.25")
        self.assertGreater(p["stop_pips"], 15)
        p = fxexit.build_plan(ns(dir=self.dir, pair="USDJPY", side="buy", entry=159.80, stop="pips:20",
                                 now="2026-11-13 09:30"), self.cfg)
        self.assertEqual((p["stop"], p["target"]), (159.6, 160.2))

    def test_refusals(self):
        self.entry()
        for kw in (dict(stop="pips:3"), dict(stop="1.1040"), dict(target="1.1070"), dict(flat_by="09:00"), dict(stop="abc")):
            with self.assertRaises(fx.FxError, msg=str(kw)):
                fxexit.build_plan(ns(dir=self.dir, **kw), self.cfg)

    def test_stop_rounds_away(self):
        self.assertEqual(fxexit.away("EURUSD", 1.106135, "sell", "stop"), 1.10614)
        self.assertEqual(fxexit.away("EURUSD", 1.106135, "buy", "stop"), 1.10613)


class TestTimeMachine(Base):
    def test_run_is_repeatable(self):
        p = self.plan()
        d = tm.run(p, self.cfg, ns())
        mc = d["mc"]
        self.assertEqual((d["pool_days"], mc["bars_left"]), (57, 85))
        self.assertEqual((mc["p_target"], mc["p_stop"], mc["p_neither"]), (0.3333, 0.549, 0.1177))
        self.assertAlmostEqual(mc["p_target"] + mc["p_stop"] + mc["p_neither"], 1.0)
        self.assertEqual(tm.run(p, self.cfg, ns())["mc"], mc)
        self.assertNotEqual(tm.run(p, self.cfg, ns(seed=7))["mc"]["p_target"], mc["p_target"])
        h = d["history"]
        self.assertEqual((h["all"]["fired"], h["all"]["target"], h["all"]["stop"], h["all"]["neither"]), (52, 12, 25, 15))
        self.assertEqual(h["same_side"]["fired"], 30)
        self.assertIn("moneda al aire", d["verdict"])

    def test_no_lookahead(self):
        p = self.plan()
        d = tm.run(p, self.cfg, ns())
        self.assertLess(d["pool_to"], p["date"])
        self.assertTrue(all(r["date"] < p["date"] for r in d["history"]["rows"]))

    def test_verdict(self):
        mk = lambda t, s, r: {"p_target": t, "p_stop": s, "r_at_target": r}
        self.assertIn("moneda", tm.verdict(mk(0.33, 0.67, 2.0))[0])
        self.assertIn("fuerza hacia el stop", tm.verdict(mk(0.2, 0.8, 1.0))[0])
        self.assertIn("hacia el objetivo", tm.verdict(mk(0.6, 0.4, 1.0))[0])


class TestBudgetRisk(Base):
    def test_size(self):
        o = self.order()
        self.assertEqual((o["units"], o["lots"], o["pip_value"], o["max_loss"]), (43000, 0.43, 4.3, 49.45))
        self.assertLessEqual(o["max_loss"], 50)
        p = self.plan()
        self.assertEqual(size.size(p, self.cfg, 1.0, p["entry"], max_loss=25)["units"], 21000)
        with self.assertRaises(fx.FxError):
            size.size(p, self.cfg, 1.0, p["entry"], max_loss=1)
        o = size.size(p, self.cfg, 1.0, p["entry"], max_loss=5000, balance=1000)
        self.assertEqual(o["decided_by"], "el margen maximo")
        self.assertLessEqual(o["margin"], 500)

    def test_jpy_conversion(self):
        p = fxexit.build_plan(ns(dir=self.dir, pair="USDJPY", side="buy", entry=160.0, stop="pips:19",
                                 now="2026-11-13 09:30"), self.cfg)
        o = size.size(p, self.cfg, 1 / 160.0, 1.0)          # 20 pips con spread = 0.20 yenes = 0.00125 USD por unidad
        self.assertEqual((o["units"], o["max_loss"]), (40000, 50.0))

    def cal(self, at="2026-11-13 09:00"):
        events = econ.parse_feed(open(CAL).read())
        return {"fetched_utc": fx.parse_now(at).strftime("%Y-%m-%dT%H:%M"), "events": events}

    def verdict(self, o, now="2026-11-13 09:28", journal=None, cal="ok", **cfg):
        c = dict(self.cfg, **cfg)
        return check.check_order(o, c, fx.parse_now(now), journal or {"trades": []}, self.cal() if cal == "ok" else cal)

    def test_pass(self):
        v = self.verdict(self.order())
        self.assertEqual((v["verdict"], v["reasons"]), ("PASA", []))

    def test_blocks(self):
        o = self.order()
        why = lambda v: " ".join(v["reasons"])
        self.assertIn("calendario", why(self.verdict(o, cal=None)))
        self.assertIn("calendario", why(self.verdict(o, cal=self.cal("2026-11-12 09:00"))))
        self.assertEqual(self.verdict(o, cal=None, news_check=False)["verdict"], "PASA")
        self.assertIn("senal", why(self.verdict(o, now="2026-11-13 10:00")))
        self.assertIn("cerrado", why(self.verdict(o, now="2026-11-14 10:00")))
        self.assertIn("maximo por operacion", why(self.verdict(o, max_loss_per_trade=40)))
        self.assertIn("R neto", why(self.verdict(o, min_reward_risk=2.0)))
        self.assertIn("bloqueados", why(self.verdict(o, blocked=["EURUSD"])))
        self.assertIn("margen", why(self.verdict(o, max_margin_pct=10)))
        self.assertIn("Falta el stop", why(self.verdict(dict(o, stop_loss=None))))
        self.assertIn("lado equivocado", why(self.verdict(dict(o, stop_loss=1.10))))
        self.assertIn("mal formada", why(self.verdict(dict(o, units=43500))))
        lost = {"trades": [{"id": "a", "day": o["date"], "pair": "USDJPY", "status": "closed", "result": -120.0}]}
        self.assertIn("Limite diario", why(self.verdict(o, journal=lost)))
        three = {"trades": [{"id": str(i), "day": o["date"], "pair": "USDJPY", "status": "closed", "result": 1.0} for i in range(3)]}
        self.assertIn("operaciones hoy", why(self.verdict(o, journal=three)))
        open_ = {"trades": [{"id": "b", "day": o["date"], "pair": "GBPUSD", "status": "open", "max_loss": 10.0}]}
        self.assertIn("comparte divisa", why(self.verdict(o, journal=open_)))
        same = {"trades": [{"id": o["id"], "day": "2026-11-12", "pair": "AUDNZD", "status": "closed", "result": 0.0}]}
        self.assertIn("ya esta en el diario", why(self.verdict(o, journal=same)))

    def test_news_blackout(self):
        o = dict(self.order(), pair="USDCAD", entry_utc=fx.ts_of(fx.parse_now("2026-11-16 08:10")),
                 flat_by_utc=fx.ts_of(fx.parse_now("2026-11-16 16:30")), date="2026-11-16",
                 entry=1.40, stop_loss=1.4015, take_profit=1.3970)
        v = check.check_order(o, self.cfg, fx.parse_now("2026-11-16 08:12"), {"trades": []}, self.cal("2026-11-16 07:00"))
        self.assertEqual(v["verdict"], "BLOQUEA")
        self.assertTrue(any("CPI" in r for r in v["reasons"]))
        self.assertTrue(any("Warsh" in w for w in v["warnings"]))

    def test_fresh_price_measures_the_loss(self):
        o = self.order()
        v = check.check_order(o, self.cfg, fx.parse_now("2026-11-13 09:28"), {"trades": []}, self.cal(), fresh=1.1040)
        self.assertEqual(v["verdict"], "BLOQUEA")           # 10.9 pips mas lejos del stop: la perdida ya no cabe
        v = check.check_order(o, self.cfg, fx.parse_now("2026-11-13 09:28"), {"trades": []}, self.cal(), fresh=1.1055)
        self.assertEqual(v["verdict"], "PASA")              # a favor del stop: se mide desde la entrada del plan

    def test_ticket_ready(self):
        o = self.order()
        now = fx.parse_now("2026-11-13 09:29")
        ok = {"checked_utc": fx.ts_of(now) - 60, "verdicts": [{"id": o["id"], "verdict": "PASA", "reasons": []}]}
        self.assertTrue(ticket.ready(o, ok, now)[0])
        self.assertFalse(ticket.ready(o, None, now)[0])
        self.assertFalse(ticket.ready(o, dict(ok, checked_utc=fx.ts_of(now) - 3600), now)[0])
        self.assertFalse(ticket.ready(dict(o, id="otra"), ok, now)[0])
        bad = {"checked_utc": fx.ts_of(now), "verdicts": [{"id": o["id"], "verdict": "BLOQUEA", "reasons": ["x"]}]}
        self.assertFalse(ticket.ready(o, bad, now)[0])


class TestCalendar(Base):
    def test_feed(self):
        ev = econ.parse_feed(open(CAL).read())
        self.assertEqual(len(ev), 111)            # 120 en el feed; 9 son de divisas fuera de las 8
        cpi = next(e for e in ev if e["title"] == "CPI m/m" and e["currency"] == "CAD")
        self.assertEqual((cpi["utc"], cpi["impact"]), ("2026-11-16T13:30", "high"))
        doc = {"events": ev}
        near = econ.events_near(doc, "USDCAD", fx.parse_now("2026-11-16 08:10"), 30)
        self.assertEqual(len(near), 3)
        self.assertEqual(econ.events_near(doc, "EURJPY", fx.parse_now("2026-11-16 08:10"), 30), [])
        self.assertEqual(econ.events_near(doc, "USDCAD", fx.parse_now("2026-11-16 07:00"), 30), [])
        with self.assertRaises(fx.FxError):
            econ.parse_feed("<html>rate limited</html>")


class TestRepo(unittest.TestCase):
    def test_every_skill_has_its_files(self):
        tools = {"fx-scanner": "scan.py", "fx-calendar": "econ.py", "fx-entry": "entry.py", "fx-exit": "exit.py",
                 "fx-timemachine": "timemachine.py", "fx-budget": "size.py", "fx-risk": "check.py",
                 "fx-ticket": "ticket.py", "fx-alerts": "alerts.py"}
        for folder, tool in tools.items():
            self.assertTrue(os.path.exists(os.path.join(SK, folder, tool)), folder)
            text = open(os.path.join(SK, folder, "SKILL.md"), encoding="utf-8").read()
            self.assertTrue(text.startswith("---\nname: %s\n" % folder), folder)
            self.assertIn(tool, text)
        json.load(open(os.path.join(SK, "fx-common", "config.example.json")))

    def test_no_tool_can_place_an_order(self):
        for folder in os.listdir(SK):
            if not folder.startswith("fx-"):
                continue
            for f in os.listdir(os.path.join(SK, folder)):
                if f.endswith(".py"):
                    src = open(os.path.join(SK, folder, f), encoding="utf-8").read()
                    self.assertNotIn("method=\"POST\"", src)
                    self.assertNotIn("data=", src.replace("data_time", ""), "%s/%s" % (folder, f))


if __name__ == "__main__":
    unittest.main()
