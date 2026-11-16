---
name: fx-risk
description: >-
  Control de riesgo de forex. Revisa cada orden contra tus limites antes de que llegue al ticket y dice PASA
  o BLOQUEA con el motivo: stop obligatorio, perdida maxima por operacion medida con spread y precio fresco,
  R neto minimo, limite de perdida diaria, maximo de operaciones al dia, mercado abierto, senal reciente,
  tiempo hasta la hora de cierre, margen, dos posiciones con la misma divisa, y datos de impacto alto del
  calendario a menos de 30 minutos. Usar cuando el usuario diga "revisa mi orden", "puedo tomar esta
  operacion", "rompe mis reglas", "cuanto he arriesgado hoy", "risk check", o siempre antes de /fx-ticket.
argument-hint: ""
---

# fx-risk

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"              # fx/orders.json -> fx/risk.json
python3 "${CLAUDE_SKILL_DIR}/check.py" --no-price   # sin pedir un precio fresco
```

## Que bloquea

| control | limite en fx/config.json |
| --- | --- |
| mercado cerrado (viernes 17:00 a domingo 17:00 de Nueva York, 25 dic, 1 ene) | |
| par en la lista de bloqueados, u orden mal formada | `blocked`, `lot_step_units` |
| falta el stop o esta del lado equivocado | |
| perdida en el stop, con spread, medida desde el peor entre la entrada del plan y el precio de ahora | `max_loss_per_trade` |
| R neto de spread por debajo del minimo | `min_reward_risk` |
| perdido hoy + riesgo de lo abierto + esta orden | `max_daily_loss` |
| operaciones del dia de forex (17:00 a 17:00 de Nueva York) | `max_trades_per_day` |
| la senal tiene mas de 15 minutos | `max_signal_age_min` |
| faltan menos de 30 minutos para la hora de cierre | `flat_by` |
| dato de impacto alto de una de las dos divisas a +-30 minutos | `news_blackout_min` |
| no hay calendario, o tiene mas de 12 horas | `news_check` |
| margen sobre el tope | `max_margin_pct` |
| ya hay una posicion abierta que comparte divisa (EURUSD y GBPUSD son la misma apuesta contra el dolar) | `max_positions_per_currency` |
| la misma orden ya esta en el diario | |

Avisa, sin bloquear, de los datos de impacto alto entre ahora y la hora de cierre.

## Pasos

1. Si no hay calendario reciente, corre `/fx-calendar` primero.
2. Corre `check.py`. Di PASA o BLOQUEA y cada motivo tal cual.
3. BLOQUEA: ahi termina. No cambies un limite, no achiques la orden y no muevas el stop para que pase. Si el
   usuario quiere cambiar un limite, que lo cambie el en `fx/config.json`, en frio y no en medio de una operacion.
4. PASA: di que es una revision de reglas y no una recomendacion. Sigue con `/fx-ticket` antes de 10 minutos.

La cadena completa: `/fx-scanner` -> `/fx-calendar` -> `/fx-entry` -> `/fx-exit` -> `/fx-timemachine` -> `/fx-budget` -> `/fx-risk` -> `/fx-ticket`, y `/fx-alerts` mientras la operacion esta abierta.
Cada skill deja su archivo en la carpeta `fx/` del proyecto y la siguiente lo lee. `${CLAUDE_SKILL_DIR}` es la carpeta de esta skill.

## Seguridad

- Educacion y herramientas, no asesoria financiera. La mayoria de quienes hacen day trading pierden dinero, y el apalancamiento del forex lo acelera.
- Ninguna herramienta de este paquete se conecta a un broker ni puede enviar una orden. El usuario pone cada orden a mano.
- Cuenta demo por defecto (`"paper": true`). Pasar a dinero real es decision del usuario, en su propia configuracion.
- Los precios son de Yahoo: indicativos, sin bid ni ask, y pueden ir con retraso. El precio real es el del broker.
- Nunca digas que par operar ni en que direccion. El usuario elige; las herramientas describen y calculan.
- Nunca cambies un limite de `fx/config.json` para que una orden pase.
