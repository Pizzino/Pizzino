#!/usr/bin/env python3
"""Control de riesgo (fx-risk). Revisa cada orden contra tus limites. PASA o BLOQUEA, con el motivo.

    python3 check.py                 # revisa fx/orders.json -> fx/risk.json
    python3 check.py --no-price      # sin pedir un precio fresco

Bloquea cuando:
  - el mercado esta cerrado, el par esta en tu lista "blocked" o la orden esta mal formada
  - falta el stop, o esta del lado equivocado
  - la perdida en el stop (con spread, medida desde el peor entre la entrada del plan y el precio
    de ahora) supera max_loss_per_trade
  - el R neto de spread es menor que min_reward_risk
  - lo ya perdido hoy + el riesgo de lo abierto + esta orden supera max_daily_loss
  - ya hiciste max_trades_per_day operaciones hoy (el dia de forex va de 17:00 a 17:00 de Nueva York)
  - la senal tiene mas de max_signal_age_min (15) minutos, o falta menos de 30 minutos para flat_by
  - hay un dato de impacto alto de una de las dos divisas a +-news_blackout_min (30) minutos,
    o el calendario falta o tiene mas de 12 horas (corre /fx-calendar; "news_check": false lo apaga)
  - el margen supera max_margin_pct del saldo
  - ya tienes abierta una posicion con una de las dos divisas (max_positions_per_currency)
  - la misma orden ya esta en el diario

Avisa (sin bloquear) de los datos de impacto alto entre ahora y flat_by.
Un PASA es una revision de reglas, no una recomendacion. Codigo 0 = todo pasa, 1 = algo se bloqueo.
"""
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "fx-common"))
sys.path.insert(0, os.path.join(HERE, "..", "fx-calendar"))
import fxlib as fx  # noqa: E402
import econ  # noqa: E402


def day_stats(journal, day):
    """Lo del dia de forex: operaciones, perdida realizada y riesgo abierto."""
    trades = [t for t in (journal or {}).get("trades", []) if t.get("day") == day]
    realized = sum(t.get("result", 0.0) for t in trades if t.get("status") == "closed")
    open_ = [t for t in (journal or {}).get("trades", []) if t.get("status") == "open"]
    return {"count": len(trades), "realized": realized, "open": open_,
            "open_risk": sum(t.get("max_loss", 0.0) for t in open_)}


def check_order(o, cfg, now, journal, calendar, fresh=None):
    block, warn = [], []
    acct = cfg["account_currency"]
    try:
        pair = fx.norm_pair(o.get("pair", ""))
    except fx.FxError as e:
        return {"id": o.get("id"), "verdict": "BLOQUEA", "reasons": [str(e)], "warnings": []}
    side, units = o.get("side"), o.get("units")
    entry, stop, target = o.get("entry"), o.get("stop_loss"), o.get("take_profit")
    step = int(cfg["lot_step_units"])
    if side not in ("buy", "sell") or not isinstance(units, int) or units <= 0 or units % step or not entry:
        block.append("Orden mal formada (lado, unidades en multiplos de %d, entrada)." % step)
        return {"id": o.get("id"), "verdict": "BLOQUEA", "reasons": block, "warnings": warn}
    long = side == "buy"
    if not fx.market_open(now):
        block.append(fx.closed_reason(now))
    if pair in [str(p).upper() for p in cfg["blocked"]]:
        block.append("%s esta en tu lista de pares bloqueados." % pair)
    if not stop:
        block.append("Falta el stop. Sin stop no hay orden.")
    elif (long and stop >= entry) or (not long and stop <= entry):
        block.append("El stop %s esta del lado equivocado de la entrada %s." % (fx.fmt(pair, stop), fx.fmt(pair, entry)))
    else:
        ref = entry
        if fresh:
            ref = max(entry, fresh) if long else min(entry, fresh)
            moved = fx.to_pips(pair, abs(fresh - entry))
            if ref != entry and moved >= 1:
                warn.append("El precio de ahora (%s) ya esta %.1f pips mas alla de la entrada del plan: la perdida se mide desde ahi." % (fx.fmt(pair, fresh), moved))
        q2a = o.get("quote_to_account") or 1.0
        loss = (abs(ref - stop) + o.get("spread_pips", fx.spread_pips(pair, cfg)) * fx.pip(pair)) * units * q2a
        if loss > cfg["max_loss_per_trade"] + 0.005:
            block.append("La perdida en el stop seria %.2f %s y tu maximo por operacion es %.2f." % (loss, acct, cfg["max_loss_per_trade"]))
        st = day_stats(journal, o.get("date"))
        lost = max(0.0, -st["realized"])
        if lost + st["open_risk"] + loss > cfg["max_daily_loss"] + 0.005:
            block.append("Limite diario: perdido hoy %.2f + riesgo abierto %.2f + esta orden %.2f supera %.2f %s." % (
                lost, st["open_risk"], loss, cfg["max_daily_loss"], acct))
        if st["count"] >= cfg["max_trades_per_day"]:
            block.append("Ya hiciste %d operaciones hoy (maximo %d)." % (st["count"], cfg["max_trades_per_day"]))
        curs = (pair[:3], pair[3:])
        clash = [t["pair"] for t in st["open"] if t["pair"][:3] in curs or t["pair"][3:] in curs]
        if len(clash) >= cfg["max_positions_per_currency"]:
            block.append("Ya tienes abierta %s, que comparte divisa con %s: seria doblar la misma apuesta." % (", ".join(clash), pair))
        if any(t.get("id") == o.get("id") for t in (journal or {}).get("trades", [])):
            block.append("Esta misma orden ya esta en el diario.")
    if target and stop:
        if (long and target <= entry) or (not long and target >= entry):
            block.append("El objetivo %s esta del lado equivocado de la entrada." % fx.fmt(pair, target))
        elif o.get("net_r") is not None and o["net_r"] < cfg["min_reward_risk"]:
            block.append("R neto %.2f, menor que tu minimo de %.2f." % (o["net_r"], cfg["min_reward_risk"]))
    margin = o.get("margin", 0.0)
    cap = cfg["balance"] * cfg["max_margin_pct"] / 100.0
    if margin > cap + 0.005:
        block.append("El margen %.2f %s supera el %g %% de tu saldo (%.2f)." % (margin, acct, cfg["max_margin_pct"], cap))
    if o.get("entry_utc"):
        age = (now - fx.utc_of(o["entry_utc"])).total_seconds() / 60.0
        lim = cfg.get("max_signal_age_min", 15)
        if age > lim:
            block.append("La senal es de las %s de Nueva York, hace %d minutos (maximo %d). El precio ya se movio: vuelve a /fx-entry." % (
                o.get("entry_time"), age, lim))
    if o.get("flat_by_utc"):
        left = (fx.utc_of(o["flat_by_utc"]) - now).total_seconds() / 60.0
        if left < 30:
            block.append("Faltan %d minutos para flat_by (%s de Nueva York): no hay tiempo para una entrada nueva." % (max(0, left), o.get("flat_by")))
    if cfg["news_check"]:
        if not calendar or econ.age_hours(calendar, now) > econ.MAX_AGE_H:
            block.append("No hay calendario economico reciente. Corre /fx-calendar (o pon \"news_check\": false).")
        else:
            near = econ.events_near(calendar, pair, now, cfg["news_blackout_min"])
            for e in near:
                block.append("Dato de impacto alto a las %s de Nueva York: %s %s (a menos de %d minutos)." % (
                    fx.hhmm(econ.ev_utc(e)), e["currency"], e["title"], cfg["news_blackout_min"]))
            if o.get("flat_by_utc"):
                end = fx.utc_of(o["flat_by_utc"])
                for e in calendar.get("events", []):
                    t = econ.ev_utc(e)
                    if e["impact"] == "high" and e["currency"] in (pair[:3], pair[3:]) and now < t <= end and e not in near:
                        warn.append("Dato de impacto alto mientras la operacion estaria abierta: %s %s a las %s de Nueva York." % (
                            e["currency"], e["title"], fx.hhmm(t)))
    return {"id": o.get("id"), "pair": pair, "verdict": "BLOQUEA" if block else "PASA", "reasons": block, "warnings": warn}


def main():
    ap = fx.argparse.ArgumentParser(description="Control de riesgo: PASA o BLOQUEA.")
    fx.common_args(ap)
    ap.add_argument("--no-price", action="store_true")
    a = ap.parse_args()
    cfg = fx.load_config(a)
    d = fx.state_dir(a)
    doc = fx.read_json(os.path.join(d, "orders.json"))
    if not doc or not doc.get("orders"):
        raise fx.FxError("No hay ordenes en fx/orders.json. Corre /fx-budget primero.")
    now = fx.resolve_now(a)
    journal = fx.read_json(os.path.join(d, "journal.json"), {"trades": []})
    calendar = fx.read_json(os.path.join(d, "calendar.json"))
    out = []
    for o in doc["orders"]:
        fresh = None
        if not (a.no_price or a.offline or a.now):
            try:
                fresh = fx.last_price(fx.norm_pair(o.get("pair", "")))
            except fx.FxError:
                fresh = None
        out.append(check_order(o, cfg, now, journal, calendar, fresh))
    res = {"checked_utc": fx.ts_of(now), "checked": fx.stamp(now), "verdicts": out}
    fx.write_json(os.path.join(d, "risk.json"), res)
    if a.json:
        print(fx.json.dumps(res, indent=2, ensure_ascii=False))
    else:
        for v in out:
            print("%s  %s (orden %s)" % (v["verdict"], v.get("pair", "?"), v["id"]))
            for r in v["reasons"]:
                print("  - %s" % r)
            for w in v["warnings"]:
                print("  aviso: %s" % w)
        if all(v["verdict"] == "PASA" for v in out):
            print("Paso la revision de reglas a las %s. No es una recomendacion. Sigue: /fx-ticket." % fx.stamp(now))
        else:
            print("Bloqueada. No se arma ticket. No cambies un limite para que pase.")
    return 0 if all(v["verdict"] == "PASA" for v in out) else 1


if __name__ == "__main__":
    fx.run(main)
