#!/usr/bin/env python3
"""Time Machine de forex (fx-timemachine). Repite la operacion antes de arriesgar dinero.

    python3 timemachine.py run             # lee fx/plan.json: 10.000 repeticiones, semilla 19
    python3 timemachine.py run --write     # guarda fx/timemachine.json
    python3 timemachine.py run --replays 20000 --seed 7

Como funciona:
  1. La bolsa de velas. Baja 60 dias de velas de 5 minutos del par y las separa por dia de
     forex (17:00 a 17:00 de Nueva York, 288 velas). Solo entran dias casi completos y
     anteriores al plan. Cada vela se guarda como tres razones contra el cierre anterior:
     maximo, minimo y cierre.
  2. Una repeticion. Empieza en la entrada. Para cada vela que queda hasta flat_by, saca al
     azar una vela pasada de la misma hora del dia (mas o menos 2 velas) y la aplica al precio.
     Vela a vela mira primero el stop y despues el objetivo: si una vela toca los dos, cuenta el stop.
  3. 10.000 repeticiones dan tres probabilidades: objetivo primero, stop primero, o ninguno
     (la operacion sigue abierta a la hora de cierre y se cierra ahi).
  4. La historia. La misma regla (el mismo rango, la misma regla de stop, el mismo R) se vuelve
     a correr en cada dia pasado. Eso es lo que paso de verdad, no una simulacion.
  5. El veredicto sale de los numeros, con el spread descontado. Un objetivo de R neto
     necesita ganar 1 de cada (1 + R) veces para quedar en cero.

Limites que hay que decir: 60 dias es una muestra chica; las velas se sacan una a una, asi que
la simulacion no conserva rachas de volatilidad ni tendencias; un hueco de precio puede llenar
el stop peor que -1R. Es una simulacion con las velas recientes del par, no una prediccion.
"""
import datetime
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "fx-common"))
sys.path.insert(0, os.path.join(HERE, "..", "fx-exit"))
import fxlib as fx  # noqa: E402
import exit as fxexit  # noqa: E402

DAY_BARS = 288
MIN_DAYS = 20


def slot_of(ts):
    """Posicion de la vela dentro del dia de forex: 0 = la de las 17:00 de Nueva York."""
    ny = fx.to_local(fx.utc_of(ts), "ny")
    return ((ny.hour * 60 + ny.minute) - 17 * 60) % 1440 // 5


def split_days(bars):
    days = {}
    for b in bars:
        days.setdefault(fx.fx_day(fx.utc_of(b["t"])), {})[slot_of(b["t"])] = b
    return days


def build_pool(days, before):
    """pool[i] = (h, l, c) / cierre de la vela anterior, de cada dia pasado casi completo."""
    pool = [[] for _ in range(DAY_BARS)]
    used = []
    for d in sorted(days):
        D = days[d]
        if d >= before or len(D) < 0.9 * DAY_BARS:
            continue
        used.append(d)
        for i in range(1, DAY_BARS):
            if i in D and i - 1 in D:
                pc = D[i - 1]["c"]
                pool[i].append((D[i]["h"] / pc, D[i]["l"] / pc, D[i]["c"] / pc))
    return pool, used


def simulate(pool, side, entry, stop, target, k, last, spread, replays=10000, seed=19, window=2):
    long = side == "buy"
    risk = abs(entry - stop)
    unit = risk + spread                      # 1R neto: la distancia al stop mas el spread
    r_target = (abs(target - entry) - spread) / unit
    rng = random.Random(seed)
    cnt = {"target": 0, "stop": 0, "close": 0}
    Rs, closes = [], []
    slots = []
    for i in range(k + 1, last + 1):
        cands = [j for j in range(max(1, i - window), min(DAY_BARS - 1, i + window) + 1) if pool[j]]
        if cands:
            slots.append(cands)
    for _ in range(replays):
        p = entry
        out = None
        for cands in slots:
            h, l, c = rng.choice(pool[rng.choice(cands)])
            hi, lo = p * h, p * l
            if long:
                if lo <= stop:
                    out = "stop"
                elif hi >= target:
                    out = "target"
            else:
                if hi >= stop:
                    out = "stop"
                elif lo <= target:
                    out = "target"
            if out:
                break
            p *= c
        if out == "target":
            Rs.append(r_target)
        elif out == "stop":
            Rs.append(-1.0)
        else:
            out = "close"
            move = (p - entry) if long else (entry - p)
            Rs.append((move - spread) / unit)
            closes.append(p)
        cnt[out] += 1
    closes.sort()

    def pct(q):
        return closes[min(len(closes) - 1, int(q * len(closes)))] if closes else None
    return {"replays": replays, "seed": seed, "window": window, "bars_left": len(slots),
            "p_target": round(cnt["target"] / replays, 4), "p_stop": round(cnt["stop"] / replays, 4),
            "p_neither": round(cnt["close"] / replays, 4), "avg_R": round(statistics.mean(Rs), 3),
            "r_at_target": round(r_target, 3),
            "open_at_close": {"p5": pct(0.05), "median": pct(0.5), "p95": pct(0.95)}}


def history(days, used, plan, cfg, spread):
    """La misma regla en cada dia pasado. Cuenta las dos direcciones y aparte la del plan."""
    name = plan.get("session")
    if plan.get("setup") != "session" or name not in fx.SESSIONS:
        return None
    pair = plan["pair"]
    rule = plan["stop_rule"]
    fixed = abs(plan["entry"] - plan["stop"])
    flat = fx.parse_clock(plan["flat_by"])
    rows = []
    all_bars = {}
    for d in used:
        for b in days[d].values():
            all_bars[b["t"]] = b
    # el rango de Londres empieza la tarde anterior en Nueva York: se mira la serie completa
    series = sorted(all_bars.values(), key=lambda b: b["t"])
    for d in used:
        try:
            rs, re_, eu = fx.session_window(name, d, cfg)
        except fx.FxError:
            return None
        rng = fx.range_of(series, rs, re_)
        if not rng:
            continue
        br = fx.find_break(series, rng, re_, eu)
        if not br:
            continue
        side, entry = br["side"], br["price"]
        long = side == "buy"
        if rule in ("range-mid", "range-far"):
            try:
                stop, _ = fxexit.stop_from_rule(rule, pair, side, entry, rng["high"], rng["low"])
            except fx.FxError:
                continue
        else:
            stop = entry - fixed if long else entry + fixed
        risk = (entry - stop) if long else (stop - entry)
        if risk <= 0:
            continue
        target = entry + plan["target_r"] * risk if long else entry - plan["target_r"] * risk
        try:
            end = fx.ts_of(fxexit.flat_by_utc(fx.utc_of(br["close_t"]), flat))
        except fx.FxError:
            continue
        out, lastc = "close", entry
        for b in series:
            if b["t"] < br["close_t"]:
                continue
            if b["t"] >= end:
                break
            lastc = b["c"]
            if (long and b["l"] <= stop) or (not long and b["h"] >= stop):
                out = "stop"
                break
            if (long and b["h"] >= target) or (not long and b["l"] <= target):
                out = "target"
                break
        unit = risk + spread
        if out == "target":
            r = (abs(target - entry) - spread) / unit
        elif out == "stop":
            r = -1.0
        else:
            r = (((lastc - entry) if long else (entry - lastc)) - spread) / unit
        rows.append({"date": d.isoformat(), "side": side, "outcome": out, "R": round(r, 2)})

    def tally(rs):
        return {"fired": len(rs), "target": sum(1 for x in rs if x["outcome"] == "target"),
                "stop": sum(1 for x in rs if x["outcome"] == "stop"),
                "neither": sum(1 for x in rs if x["outcome"] == "close"),
                "avg_R": round(statistics.mean(x["R"] for x in rs), 3) if rs else None}
    return {"sessions": len(used), "all": tally(rows),
            "same_side": tally([x for x in rows if x["side"] == plan["side"]]), "rows": rows}


def verdict(mc):
    hit = mc["p_target"] + mc["p_stop"]
    need = 1.0 / (1.0 + mc["r_at_target"]) if mc["r_at_target"] > -1 else 1.0
    if hit < 0.05:
        return "Casi ninguna repeticion toco el stop o el objetivo: el plan depende del precio a la hora de cierre.", need, None
    got = mc["p_target"] / hit
    gap = (got - need) * 100
    if abs(gap) < 5:
        text = "Cerca del punto de equilibrio: practicamente una moneda al aire."
    elif abs(gap) < 15:
        text = "Se inclina hacia el %s." % ("objetivo" if gap > 0 else "stop")
    else:
        text = "Se inclina con fuerza hacia el %s." % ("objetivo" if gap > 0 else "stop")
    return text, need, got


def run(plan, cfg, a):
    pair = plan["pair"]
    res = fx.load_chart(pair, "60d", "5m", a.offline)
    entry_utc = fx.utc_of(plan["entry_utc"])
    bars = fx.bars_from(res, entry_utc, "5m")
    days = split_days(bars)
    plan_day = fx.fx_day(entry_utc - datetime.timedelta(seconds=1))
    pool, used = build_pool(days, plan_day)
    if len(used) < MIN_DAYS:
        raise fx.FxError("Solo hay %d dias completos de velas antes del plan (minimo %d). No alcanza para una simulacion justa." % (len(used), MIN_DAYS))
    k = slot_of(plan["entry_utc"] - 300)
    last = slot_of(plan["flat_by_utc"] - 300)
    if last <= k:
        raise fx.FxError("No quedan velas entre la entrada y flat_by.")
    spread = plan["spread_pips"] * fx.pip(pair)
    mc = simulate(pool, plan["side"], plan["entry"], plan["stop"], plan["target"], k, last, spread,
                  a.replays, a.seed, a.window)
    hist = history(days, used, plan, cfg, spread)
    text, need, got = verdict(mc)
    return {"plan": plan, "pool_days": len(used), "pool_from": used[0].isoformat(), "pool_to": used[-1].isoformat(),
            "mc": mc, "history": hist, "verdict": text, "needs": round(need, 4),
            "got": round(got, 4) if got is not None else None}


def report(doc):
    p, mc, pair = doc["plan"], doc["mc"], doc["plan"]["pair"]
    print("Time Machine: %s %s, entrada %s, stop %s, objetivo %s (%.2fR neto tras %.1f pips de spread)." % (
        "COMPRA" if p["side"] == "buy" else "VENTA", pair, fx.fmt(pair, p["entry"]), fx.fmt(pair, p["stop"]),
        fx.fmt(pair, p["target"]), mc["r_at_target"], p["spread_pips"]))
    print("%s repeticiones de las %d velas hasta las %s de Nueva York, con velas de %d dias (%s a %s). Semilla %d." % (
        format(mc["replays"], ",").replace(",", "."), mc["bars_left"], p["flat_by"], doc["pool_days"],
        doc["pool_from"], doc["pool_to"], mc["seed"]))
    print("  Objetivo primero  %5.1f %%" % (mc["p_target"] * 100))
    print("  Stop primero      %5.1f %%" % (mc["p_stop"] * 100))
    print("  Ninguno           %5.1f %%  (se cierra a las %s)" % (mc["p_neither"] * 100, p["flat_by"]))
    oc = mc["open_at_close"]
    if oc["median"]:
        print("  Cuando sigue abierta, el precio a esa hora: mediana %s, de %s a %s (5 %% a 95 %%)." % (
            fx.fmt(pair, oc["median"]), fx.fmt(pair, oc["p5"]), fx.fmt(pair, oc["p95"])))
    print("  R promedio neto   %+.3f" % mc["avg_R"])
    h = doc["history"]
    if h:
        for key, label in (("all", "en cualquier direccion"), ("same_side", "en la direccion del plan")):
            t = h[key]
            if t["fired"]:
                print("  Historia %s: la regla se activo %d veces en %d dias: %d objetivo, %d stop, %d ninguno; R promedio neto %+.3f." % (
                    label, t["fired"], h["sessions"], t["target"], t["stop"], t["neither"], t["avg_R"]))
            else:
                print("  Historia %s: la regla no se activo en %d dias." % (label, h["sessions"]))
    else:
        print("  Historia: no aplica a un plan manual o por nivel.")
    if doc["got"] is not None:
        print("Veredicto: %s Necesita ganar el %.0f %% de las que tocan un lado; gano el %.0f %%." % (
            doc["verdict"], doc["needs"] * 100, doc["got"] * 100))
    else:
        print("Veredicto: %s" % doc["verdict"])
    if mc["p_neither"] > 0.4:
        print("Mas del 40 % de las repeticiones no tocaron ningun lado: ahi decide el precio a la hora de cierre.")
    print("Simulacion con las velas recientes del par, no una prediccion. 60 dias es una muestra chica.")


def cmd_run(a):
    cfg = fx.load_config(a)
    plan = fx.read_json(os.path.join(fx.state_dir(a), "plan.json"))
    if not plan:
        raise fx.FxError("No hay fx/plan.json. Corre /fx-exit primero.")
    doc = run(plan, cfg, a)
    if a.json:
        print(fx.json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        report(doc)
    if a.write:
        path = os.path.join(fx.state_dir(a), "timemachine.json")
        fx.write_json(path, doc)
        if not a.json:
            print("Escribi %s. Sigue: /fx-budget." % path)
    return 0


def main():
    ap = fx.argparse.ArgumentParser(description="Time Machine de forex.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    fx.common_args(p)
    p.add_argument("--replays", type=int, default=10000)
    p.add_argument("--seed", type=int, default=19)
    p.add_argument("--window", type=int, default=2)
    p.add_argument("--write", action="store_true")
    a = ap.parse_args()
    return cmd_run(a)


if __name__ == "__main__":
    fx.run(main)
