#!/usr/bin/env python3
"""fxlib: la base que comparten las skills fx-* (forex). Solo biblioteca estandar.

Que hay aqui:
  - los 28 pares de las 8 divisas principales, el pip de cada uno y un spread tipico
  - la hora: Nueva York y Londres con su horario de verano, la semana de forex
    (abre domingo 17:00 NY, cierra viernes 17:00 NY) y las dos sesiones que se operan
  - los datos: velas gratuitas de Yahoo (no oficiales, pueden ir con retraso, sin volumen)
  - el rango de una sesion y su ruptura, en las dos direcciones
  - RSI, media y ATR, y la conversion de la divisa cotizada a la divisa de la cuenta
  - la carpeta fx/ donde cada skill deja su archivo para la siguiente

Los precios de Yahoo son indicativos (un solo precio, sin bid ni ask). Por eso cada
calculo de riesgo suma el spread aparte.
"""

import argparse
import datetime
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; fx-trader-skills/1.0)"
PAUSE = 0.4       # segundos entre peticiones al endpoint gratuito
BACKOFF = 5.0     # espera antes del unico reintento tras un HTTP 429
HOSTS = ("query2", "query1")
STEP = {"5m": 300, "1d": 86400}

# Orden de prioridad convencional: da los nombres habituales (EURUSD, no USDEUR).
CCYS = ("EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY")
PAIRS = [a + b for i, a in enumerate(CCYS) for b in CCYS[i + 1:]]
MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"]

# Spread tipico en pips de una cuenta minorista en horas liquidas. Es una suposicion:
# pon el de tu broker en fx/config.json -> "spreads_pips".
SPREADS = {"EURUSD": 1.0, "USDJPY": 1.0, "GBPUSD": 1.5, "AUDUSD": 1.2, "USDCAD": 1.8,
           "USDCHF": 1.5, "NZDUSD": 1.8, "EURGBP": 1.5, "EURJPY": 1.8, "GBPJPY": 2.5,
           "EURCHF": 2.0, "AUDJPY": 2.0}
SPREAD_OTHER = 3.0

SESSIONS = {
    # Rango asiatico (00:00 a 08:00 de Londres); la ruptura se busca tras la apertura de Londres.
    "london": {"tz": "london", "range_start": "00:00", "range_end": "08:00", "entries_until": "11:00"},
    # Primera hora de Nueva York (08:00 a 09:00, incluye los datos de las 8:30).
    "ny": {"tz": "ny", "range_start": "08:00", "range_end": "09:00", "entries_until": "12:00"},
}

DEFAULTS = {
    "account_currency": "USD",
    "balance": 5000,
    "leverage": 30,
    "max_loss_per_trade": 50,
    "max_daily_loss": 150,
    "max_trades_per_day": 3,
    "min_reward_risk": 1.0,
    "max_margin_pct": 50,
    "lot_step_units": 1000,
    "min_stop_spreads": 5,
    "flat_by": "16:30",
    "news_check": True,
    "news_blackout_min": 30,
    "max_positions_per_currency": 1,
    "pairs": MAJORS,
    "spreads_pips": {},
    "sessions": {},
    "blocked": [],
    "paper": True,
}

TZ_NAME = {"ny": "Nueva York", "london": "Londres", "utc": "UTC"}


class FxError(Exception):
    pass


# ---------------------------------------------------------------- pares

def norm_pair(text):
    """'eur/usd', 'EURUSD=X', 'eurusd' -> 'EURUSD'. Error si no es uno de los 28."""
    p = (text or "").upper().replace("/", "").replace("=X", "").replace("-", "").replace("_", "").strip()
    if p in PAIRS:
        return p
    if len(p) == 6 and p[3:] + p[:3] in PAIRS:
        raise FxError("%s se escribe %s." % (p, p[3:] + p[:3]))
    raise FxError("'%s' no es uno de los 28 pares (divisas: %s)." % (text, ", ".join(CCYS)))


def pip(pair):
    return 0.01 if pair.endswith("JPY") else 0.0001


def digits(pair):
    return 3 if pair.endswith("JPY") else 5


def fmt(pair, price):
    return "%.*f" % (digits(pair), price)


def rnd(pair, price):
    return round(price, digits(pair))


def to_pips(pair, diff):
    return round(diff / pip(pair), 1)


def spread_pips(pair, cfg=None):
    own = (cfg or {}).get("spreads_pips") or {}
    return float(own.get(pair, SPREADS.get(pair, SPREAD_OTHER)))


# ---------------------------------------------------------------- hora

def _nth_sunday(year, month, n):
    d = datetime.date(year, month, 1)
    d += datetime.timedelta(days=(6 - d.weekday()) % 7)
    return d + datetime.timedelta(weeks=n - 1)


def _last_sunday(year, month):
    d = datetime.date(year + (month == 12), month % 12 + 1, 1) - datetime.timedelta(days=1)
    return d - datetime.timedelta(days=(d.weekday() + 1) % 7)


def ny_offset(utc):
    """-4 en horario de verano de EE.UU. (2.o domingo de marzo a 1.er domingo de noviembre), si no -5."""
    y = utc.year
    start = datetime.datetime.combine(_nth_sunday(y, 3, 2), datetime.time(7, 0))
    end = datetime.datetime.combine(_nth_sunday(y, 11, 1), datetime.time(6, 0))
    return -4 if start <= utc < end else -5


def london_offset(utc):
    """+1 en horario de verano britanico (ultimo domingo de marzo a ultimo de octubre, 01:00 UTC), si no 0."""
    y = utc.year
    start = datetime.datetime.combine(_last_sunday(y, 3), datetime.time(1, 0))
    end = datetime.datetime.combine(_last_sunday(y, 10), datetime.time(1, 0))
    return 1 if start <= utc < end else 0


def _offset(utc, tz):
    return ny_offset(utc) if tz == "ny" else london_offset(utc) if tz == "london" else 0


def to_local(utc, tz):
    return utc + datetime.timedelta(hours=_offset(utc, tz))


def local_to_utc(local, tz):
    for off in ((-4, -5) if tz == "ny" else (1, 0) if tz == "london" else (0,)):
        utc = local - datetime.timedelta(hours=off)
        if _offset(utc, tz) == off:
            return utc
    return local - datetime.timedelta(hours=_offset(local, tz))


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)


def utc_of(ts):
    return datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=int(ts))


def ts_of(utc):
    return int((utc - datetime.datetime(1970, 1, 1)).total_seconds())


def parse_now(text):
    """--now 'AAAA-MM-DD HH:MM' en hora de Nueva York -> UTC."""
    try:
        local = datetime.datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        raise FxError("--now se escribe 'AAAA-MM-DD HH:MM' en hora de Nueva York, por ejemplo '2026-11-13 09:30'.")
    return local_to_utc(local, "ny")


def parse_clock(text, what="la hora"):
    try:
        h, m = str(text).strip().split(":")
        h, m = int(h), int(m)
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError
    except ValueError:
        raise FxError("%s se escribe HH:MM en 24 horas, por ejemplo 16:30 (recibi '%s')." % (what, text))
    return datetime.time(h, m)


def stamp(utc, tz="ny"):
    return "%s (%s)" % (to_local(utc, tz).strftime("%Y-%m-%d %H:%M"), TZ_NAME[tz])


def hhmm(utc, tz="ny"):
    return to_local(utc, tz).strftime("%H:%M")


def market_open(utc):
    """Forex abre el domingo a las 17:00 de Nueva York y cierra el viernes a las 17:00.
    El 25 de diciembre y el 1 de enero casi no hay mercado: se cuentan como cerrado."""
    ny = to_local(utc, "ny")
    wd = ny.weekday()
    if (ny.month, ny.day) in ((12, 25), (1, 1)):
        return False
    if wd == 5:
        return False
    if wd == 4 and ny.time() >= datetime.time(17, 0):
        return False
    if wd == 6 and ny.time() < datetime.time(17, 0):
        return False
    return True


def fx_day(utc):
    """El dia de forex va de 17:00 a 17:00 de Nueva York. Devuelve la fecha en que termina."""
    return (to_local(utc, "ny") + datetime.timedelta(hours=7)).date()


def closed_reason(utc):
    ny = to_local(utc, "ny")
    if (ny.month, ny.day) in ((12, 25), (1, 1)):
        return "Festivo: casi no hay mercado hoy."
    return "El mercado de forex esta cerrado (abre el domingo a las 17:00 de Nueva York)."


# ---------------------------------------------------------------- archivos

def state_dir(a=None):
    return getattr(a, "dir", None) or os.environ.get("FX_DIR") or "fx"


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as e:
        raise FxError("No pude leer %s: %s" % (path, e))


def write_json(path, doc):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def load_config(a=None):
    cfg = dict(DEFAULTS)
    own = read_json(os.path.join(state_dir(a), "config.json"), {}) or {}
    if not isinstance(own, dict):
        raise FxError("fx/config.json tiene que ser un objeto JSON.")
    cfg.update(own)
    cfg["account_currency"] = str(cfg["account_currency"]).upper()
    if cfg["account_currency"] not in CCYS:
        raise FxError("account_currency tiene que ser una de: %s." % ", ".join(CCYS))
    cfg["pairs"] = [norm_pair(p) for p in cfg["pairs"]]
    return cfg


def session_def(name, cfg=None):
    if name not in SESSIONS:
        raise FxError("La sesion es 'london' o 'ny' (recibi '%s')." % name)
    d = dict(SESSIONS[name])
    d.update(((cfg or {}).get("sessions") or {}).get(name) or {})
    return d


# ---------------------------------------------------------------- datos

def chart_url(pair, rng, interval, host="query2"):
    return "https://%s.finance.yahoo.com/v8/finance/chart/%s=X?range=%s&interval=%s" % (host, pair, rng, interval)


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_text(url_for_host):
    """query2 primero, query1 ante un 429 o 5xx, un solo reintento tras un 429."""
    last = None
    for attempt in range(2):
        for host in HOSTS:
            try:
                text = _get(url_for_host(host))
                time.sleep(PAUSE)
                return text
            except urllib.error.HTTPError as e:
                last = "HTTP %s" % e.code
                if e.code not in (429,) and e.code < 500:
                    raise FxError("Yahoo respondio %s." % last)
            except (urllib.error.URLError, OSError) as e:
                last = str(getattr(e, "reason", e))
        if attempt == 0:
            time.sleep(BACKOFF)
    raise FxError("No pude llegar a Yahoo (%s)." % last)


def _read_file(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return f.read()


def load_chart(pair, rng, interval, offline=None):
    """Devuelve chart.result[0] de Yahoo. offline: un archivo, o una carpeta con PAR-5m.json(.gz)."""
    if offline:
        path = offline
        if os.path.isdir(offline):
            for ext in (".json.gz", ".json"):
                path = os.path.join(offline, "%s-%s%s" % (pair, interval, ext))
                if os.path.exists(path):
                    break
            else:
                raise FxError("No hay archivo guardado de %s (%s) en %s." % (pair, interval, offline))
        try:
            text = _read_file(path)
        except OSError as e:
            raise FxError("No pude leer %s: %s" % (path, e))
    else:
        text = fetch_text(lambda host: chart_url(pair, rng, interval, host))
    try:
        doc = json.loads(text)
        res = doc["chart"]["result"]
        if not res:
            raise KeyError
        return res[0]
    except (ValueError, KeyError, TypeError):
        raise FxError("Yahoo no devolvio datos de %s." % pair)


def data_time(result):
    t = (result.get("meta") or {}).get("regularMarketTime")
    return utc_of(t) if t else None


def bars_from(result, now_utc, interval):
    """Velas completas y limpias: {t (epoch UTC del inicio), o, h, l, c}.
    Fuera: valores nulos, la vela en curso, el tick vivo fuera de la rejilla y,
    en 5m, las velas con el mercado cerrado (Yahoo las rellena planas)."""
    step = STEP[interval]
    ts = result.get("timestamp") or []
    try:
        q = result["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        return []
    now_ts = ts_of(now_utc)
    live = (result.get("meta") or {}).get("regularMarketTime")
    out = []
    for i, t in enumerate(ts):
        try:
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        except (KeyError, IndexError):
            continue
        if None in (o, h, l, c) or min(o, h, l, c) <= 0:
            continue
        if interval == "5m":
            if t % step or not market_open(utc_of(t)):
                continue
        elif t == live and t % 3600:
            continue
        if t + step > now_ts:
            continue
        out.append({"t": int(t), "o": o, "h": max(h, o, c), "l": min(l, o, c), "c": c})
    return out


def resolve_now(a, result=None):
    """La hora del calculo: --now, o la del archivo offline, o el reloj."""
    if getattr(a, "now", None):
        return parse_now(a.now)
    if getattr(a, "offline", None) and result is not None and data_time(result):
        return data_time(result)
    return utc_now()


# ---------------------------------------------------------------- sesiones y rupturas

def session_window(name, day, cfg=None):
    """(inicio del rango, fin del rango, ultima hora de entrada) en UTC para ese dia local de la sesion."""
    d = session_def(name, cfg)
    tz = d["tz"]

    def at(key):
        return local_to_utc(datetime.datetime.combine(day, parse_clock(d[key], key)), tz)
    rs, re_, eu = at("range_start"), at("range_end"), at("entries_until")
    if not rs < re_ < eu:
        raise FxError("La sesion '%s' necesita range_start < range_end < entries_until." % name)
    return rs, re_, eu


def session_day(name, utc, cfg=None):
    return to_local(utc, session_def(name, cfg)["tz"]).date()


def range_of(bars, rs, re_):
    """Maximo y minimo del rango. None si falta mas del 20 % de las velas (dia fino o cortado)."""
    a, b = ts_of(rs), ts_of(re_)
    inside = [x for x in bars if a <= x["t"] < b]
    expected = (b - a) // STEP["5m"]
    if expected <= 0 or len(inside) < 0.8 * expected:
        return None
    return {"high": max(x["h"] for x in inside), "low": min(x["l"] for x in inside),
            "bars": len(inside), "expected": expected}


def find_break(bars, rng, re_, eu):
    """La primera vela COMPLETA tras el rango que CIERRA fuera de el. Una mecha no cuenta.
    Devuelve None o {side, price, bar_t, close_t}. La hora de entrada es el cierre de la vela."""
    a, b = ts_of(re_), ts_of(eu)
    for x in bars:
        if x["t"] < a:
            continue
        if x["t"] + STEP["5m"] > b:
            break
        if x["c"] > rng["high"]:
            return {"side": "buy", "price": x["c"], "bar_t": x["t"], "close_t": x["t"] + STEP["5m"]}
        if x["c"] < rng["low"]:
            return {"side": "sell", "price": x["c"], "bar_t": x["t"], "close_t": x["t"] + STEP["5m"]}
    return None


# ---------------------------------------------------------------- indicadores

def sma(values, n):
    return sum(values[-n:]) / n if len(values) >= n else None


def rsi(closes, n=14):
    """RSI de Wilder."""
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def atr(bars, n=14):
    """ATR de Wilder sobre velas con h, l, c."""
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    v = sum(trs[:n]) / n
    for tr in trs[n:]:
        v = (v * (n - 1) + tr) / n
    return v


# ---------------------------------------------------------------- conversion

def last_price(pair, offline=None):
    res = load_chart(pair, "5d", "1d", offline)
    p = (res.get("meta") or {}).get("regularMarketPrice")
    if not p:
        raise FxError("Yahoo no dio precio de %s." % pair)
    return float(p)


def rate(frm, to, getter):
    """Cuantas unidades de 'to' vale una unidad de 'frm'. getter(par) da el ultimo precio."""
    if frm == to:
        return 1.0
    if frm + to in PAIRS:
        return getter(frm + to)
    if to + frm in PAIRS:
        return 1.0 / getter(to + frm)
    raise FxError("No hay par para convertir %s a %s." % (frm, to))


# ---------------------------------------------------------------- linea de comandos

def common_args(p):
    p.add_argument("--dir", help="carpeta de estado (por defecto fx/)")
    p.add_argument("--now", help="fijar el reloj: 'AAAA-MM-DD HH:MM' en hora de Nueva York")
    p.add_argument("--offline", help="archivo o carpeta con respuestas de Yahoo guardadas")
    p.add_argument("--json", action="store_true", help="salida en JSON")


def run(main_fn):
    """Envuelve el main de una herramienta: un error es una linea clara y codigo 1."""
    try:
        code = main_fn()
    except FxError as e:
        print("%s: %s" % (os.path.basename(sys.argv[0]), e), file=sys.stderr)
        code = 1
    except KeyboardInterrupt:
        code = 1
    sys.exit(code or 0)


DISCLAIMER = "Educacion y herramientas, no asesoria financiera. La mayoria de quienes hacen day trading pierden dinero."

__all__ = [n for n in dir() if not n.startswith("_")] + ["argparse"]
