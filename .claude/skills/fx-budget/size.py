#!/usr/bin/env python3
"""Tamano de posicion (fx-budget). Cuantas unidades (lotes) caben en tu perdida maxima.

    python3 size.py                       # lee fx/plan.json y fx/config.json -> fx/orders.json
    python3 size.py --max-loss 25         # otra perdida maxima para esta operacion
    python3 size.py --risk-pct 1          # o como porcentaje del saldo
    python3 size.py --balance 2000 --no-write

La cuenta:
  perdida por unidad = (distancia al stop + spread) x valor de la divisa cotizada en tu divisa
  unidades = perdida maxima / perdida por unidad, redondeado HACIA ABAJO al paso del lote
             (lot_step_units, 1.000 = un microlote; 100.000 unidades = 1 lote estandar)
  margen   = unidades x valor de la divisa base en tu divisa / apalancamiento

Dos limites, gana el menor: la perdida maxima por operacion y el margen maximo
(max_margin_pct del saldo). Si no cabe ni un paso de lote, la respuesta es un no claro,
nunca una orden mas chica con un stop mas cerca.

Escribe UNA orden en fx/orders.json. No envia nada.
"""
import hashlib
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fx-common"))
import fxlib as fx  # noqa: E402


def order_id(o):
    key = "|".join(str(o[k]) for k in ("pair", "side", "units", "entry", "stop_loss", "take_profit", "entry_utc"))
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def size(plan, cfg, q2a, b2a, max_loss=None, balance=None):
    pair = plan["pair"]
    balance = float(balance if balance is not None else cfg["balance"])
    max_loss = float(max_loss if max_loss is not None else cfg["max_loss_per_trade"])
    step = int(cfg["lot_step_units"])
    if balance <= 0 or max_loss <= 0 or step <= 0:
        raise fx.FxError("El saldo, la perdida maxima y el paso de lote tienen que ser mayores que cero.")
    dist = abs(plan["entry"] - plan["stop"]) + plan["spread_pips"] * fx.pip(pair)
    loss_per_unit = dist * q2a
    by_loss = max_loss / loss_per_unit
    by_margin = balance * cfg["max_margin_pct"] / 100.0 * cfg["leverage"] / b2a
    raw = min(by_loss, by_margin)
    units = int(math.floor(raw / step + 1e-9)) * step
    decided = "la perdida maxima por operacion" if by_loss <= by_margin else "el margen maximo"
    if units < step:
        raise fx.FxError(
            "No cabe: con el stop a %.1f pips (mas %.1f de spread) un paso de %s unidades arriesga %.2f %s, "
            "y tu maximo es %.2f. No se arma una orden mas chica ni se acerca el stop: deja pasar esta operacion." % (
                plan["stop_pips"], plan["spread_pips"], format(step, ","), loss_per_unit * step,
                cfg["account_currency"], max_loss))
    o = {
        "pair": pair, "side": plan["side"], "type": "market", "units": units, "lots": round(units / 100000.0, 3),
        "entry": plan["entry"], "stop_loss": plan["stop"], "take_profit": plan["target"],
        "stop_pips": plan["stop_pips"], "spread_pips": plan["spread_pips"],
        "target_r": plan["target_r"], "net_r": plan["net_r"],
        "account_currency": cfg["account_currency"], "quote_to_account": round(q2a, 8), "base_to_account": round(b2a, 8),
        "pip_value": round(fx.pip(pair) * units * q2a, 4),
        "max_loss": round(loss_per_unit * units, 2),
        "notional": round(units * b2a, 2), "margin": round(units * b2a / cfg["leverage"], 2),
        "leverage": cfg["leverage"], "decided_by": decided,
        "entry_time": plan["entry_time"], "entry_utc": plan["entry_utc"], "date": plan["date"],
        "flat_by": plan["flat_by"], "flat_by_utc": plan["flat_by_utc"],
    }
    o["id"] = order_id(o)
    return o


def main():
    ap = fx.argparse.ArgumentParser(description="Tamano de posicion en unidades y lotes.")
    fx.common_args(ap)
    ap.add_argument("--max-loss", type=float)
    ap.add_argument("--risk-pct", type=float)
    ap.add_argument("--balance", type=float)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    cfg = fx.load_config(a)
    plan = fx.read_json(os.path.join(fx.state_dir(a), "plan.json"))
    if not plan:
        raise fx.FxError("No hay fx/plan.json. Corre /fx-exit primero.")
    pair, acct = plan["pair"], cfg["account_currency"]
    cache = {}

    def getter(p):
        if p not in cache:
            cache[p] = plan["entry"] if p == pair else fx.last_price(p, a.offline)
        return cache[p]
    q2a = fx.rate(pair[3:], acct, getter)
    b2a = fx.rate(pair[:3], acct, getter)
    balance = a.balance if a.balance is not None else cfg["balance"]
    max_loss = a.max_loss
    if a.risk_pct is not None:
        max_loss = balance * a.risk_pct / 100.0
    o = size(plan, cfg, q2a, b2a, max_loss, balance)
    doc = {"date": plan["date"], "orders": [o]}
    if a.json:
        print(fx.json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        print("%s %s unidades de %s (%.2f lotes). Lo decidio %s." % (
            "COMPRA" if o["side"] == "buy" else "VENTA", format(o["units"], ",").replace(",", "."), pair, o["lots"], o["decided_by"]))
        print("  Entrada %s, stop %s, objetivo %s." % (fx.fmt(pair, o["entry"]), fx.fmt(pair, o["stop_loss"]), fx.fmt(pair, o["take_profit"])))
        print("  Cada pip vale %.2f %s. Si salta el stop (con %.1f pips de spread) pierdes %.2f %s." % (
            o["pip_value"], acct, o["spread_pips"], o["max_loss"], acct))
        print("  Margen %.2f %s con apalancamiento %s:1 (posicion de %.2f %s)." % (o["margin"], acct, o["leverage"], o["notional"], acct))
        print("  Un hueco de precio o un dato fuerte puede llenar el stop peor que eso.")
    if not a.no_write:
        path = os.path.join(fx.state_dir(a), "orders.json")
        fx.write_json(path, doc)
        if not a.json:
            print("Escribi %s. Sigue: /fx-risk. Nada se ha enviado." % path)
    return 0


if __name__ == "__main__":
    fx.run(main)
