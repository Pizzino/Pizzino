---
name: fx-calendar
description: >-
  Calendario economico para forex. Baja el calendario semanal gratuito de ForexFactory y muestra los datos
  que mueven cada divisa (tipos de interes, inflacion, empleo, discursos de bancos centrales), con hora de
  Nueva York, impacto, prevision y dato anterior. Guarda fx/calendar.json, que fx-risk usa para bloquear
  entradas cerca de un dato de impacto alto. Usar cuando el usuario diga "que noticias hay hoy", "calendario
  economico", "hay algun dato del dolar", "cuando es el NFP", "que mueve al euro esta semana", "economic
  calendar", "news for EURUSD", o despues de /fx-scanner y antes de /fx-entry.
argument-hint: "[PAR] [--hours N]"
---

# fx-calendar

En forex el precio lo mueven los datos macro y los bancos centrales. Alrededor de un dato de impacto alto
el spread se abre y el precio salta: un stop puede llenarse mucho peor de lo planeado. Esta skill dice que
viene y cuando.

```bash
python3 "${CLAUDE_SKILL_DIR}/econ.py" fetch                    # baja la semana -> fx/calendar.json
python3 "${CLAUDE_SKILL_DIR}/econ.py" next                     # proximas 24 h, impacto alto, tus pares
python3 "${CLAUDE_SKILL_DIR}/econ.py" next EURUSD --hours 48   # solo EUR y USD
python3 "${CLAUDE_SKILL_DIR}/econ.py" next --impact medium     # alto y medio
python3 "${CLAUDE_SKILL_DIR}/econ.py" next --currencies USD,JPY
```

## Datos y limites

- Fuente: `https://nfs.faireconomy.media/ff_calendar_thisweek.json`. Gratis, no oficial, solo la semana en
  curso (el domingo aparece la nueva).
- El feed limita las descargas: la skill lo guarda una hora y reutiliza la copia. Si la descarga falla, usa
  la copia guardada.
- Solo las 8 divisas del paquete (EUR, GBP, AUD, NZD, USD, CAD, CHF, JPY).
- Las horas se muestran en Nueva York.

## Pasos

1. Corre `econ.py next PAR` (o sin par, para los pares de la configuracion).
2. Di cada dato de impacto alto con su hora de Nueva York y cuanto falta.
3. Di que `/fx-risk` bloquea entradas a +-30 minutos (`news_blackout_min`) de un dato de impacto alto de
   cualquiera de las dos divisas del par, y avisa de los que caen mientras la operacion estaria abierta.
4. No interpretes el dato ni adivines la direccion. Un dato "mejor de lo previsto" no dice hacia donde va el precio.

La cadena completa: `/fx-scanner` -> `/fx-calendar` -> `/fx-entry` -> `/fx-exit` -> `/fx-timemachine` -> `/fx-budget` -> `/fx-risk` -> `/fx-ticket`, y `/fx-alerts` mientras la operacion esta abierta.
Cada skill deja su archivo en la carpeta `fx/` del proyecto y la siguiente lo lee. `${CLAUDE_SKILL_DIR}` es la carpeta de esta skill.

## Seguridad

- Educacion y herramientas, no asesoria financiera. La mayoria de quienes hacen day trading pierden dinero, y el apalancamiento del forex lo acelera.
- Ninguna herramienta de este paquete se conecta a un broker ni puede enviar una orden. El usuario pone cada orden a mano.
- Cuenta demo por defecto (`"paper": true`). Pasar a dinero real es decision del usuario, en su propia configuracion.
- Los precios son de Yahoo: indicativos, sin bid ni ask, y pueden ir con retraso. El precio real es el del broker.
- Nunca digas que par operar ni en que direccion. El usuario elige; las herramientas describen y calculan.
- Nunca cambies un limite de `fx/config.json` para que una orden pase.
