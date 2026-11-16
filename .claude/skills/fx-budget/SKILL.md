---
name: fx-budget
description: >-
  Tamano de posicion en forex. Calcula cuantas unidades y lotes caben en tu perdida maxima por operacion:
  lee el plan de fx-exit, suma el spread a la distancia al stop, convierte la divisa cotizada a la divisa de
  tu cuenta (pares en yenes y cruces incluidos), respeta el margen maximo segun tu apalancamiento y redondea
  hacia abajo al microlote. Dice cuanto vale cada pip y cuanto pierdes si salta el stop. Escribe UNA orden en
  fx/orders.json; no envia nada. Usar cuando el usuario diga "cuantos lotes", "que tamano de posicion",
  "tengo 5000 dolares", "quiero arriesgar el 1 %", "cuanto vale el pip", "position size", "lot size", o
  despues de /fx-timemachine.
argument-hint: "[--max-loss N | --risk-pct N]"
---

# fx-budget

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py"                  # fx/plan.json + fx/config.json -> fx/orders.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --max-loss 25    # otra perdida maxima para esta operacion
python3 "${CLAUDE_SKILL_DIR}/size.py" --risk-pct 1     # o como porcentaje del saldo
python3 "${CLAUDE_SKILL_DIR}/size.py" --balance 2000 --no-write
```

## La cuenta

```
perdida por unidad = (distancia al stop + spread) x valor de la divisa cotizada en tu divisa
unidades           = perdida maxima / perdida por unidad, redondeado HACIA ABAJO al paso del lote
margen             = unidades x valor de la divisa base en tu divisa / apalancamiento
```

- 100.000 unidades = 1 lote estandar; 10.000 = un minilote; 1.000 = un microlote (`lot_step_units`).
- Dos limites y gana el menor: `max_loss_per_trade` y `max_margin_pct` del saldo. La skill dice cual decidio.
- Si no cabe ni un paso de lote, la respuesta es un no. Nunca una orden mas chica con el stop mas cerca.
- Ejemplo real (EURUSD, 13 nov 2026): stop a 10,5 pips + 1,0 de spread, perdida maxima 50 USD ->
  43.000 unidades (0,43 lotes), 4,30 USD por pip, 49,45 USD si salta el stop.

## Configuracion

La primera vez, copia `fx-common/config.example.json` a `fx/config.json` y pregunta al usuario: divisa de
la cuenta, saldo, apalancamiento de su broker (30:1 es el tope minorista en Europa para pares mayores; 50:1
en EE.UU.), perdida maxima por operacion, perdida maxima diaria y el spread de sus pares. No inventes esos
numeros.

## Pasos

1. Corre `size.py`. Di unidades, lotes, valor del pip, perdida en el stop, margen y que limite decidio.
2. Di que un hueco de precio puede llenar el stop peor.
3. Sigue con `/fx-risk`. Nada se ha enviado.

La cadena completa: `/fx-scanner` -> `/fx-calendar` -> `/fx-entry` -> `/fx-exit` -> `/fx-timemachine` -> `/fx-budget` -> `/fx-risk` -> `/fx-ticket`, y `/fx-alerts` mientras la operacion esta abierta.
Cada skill deja su archivo en la carpeta `fx/` del proyecto y la siguiente lo lee. `${CLAUDE_SKILL_DIR}` es la carpeta de esta skill.

## Seguridad

- Educacion y herramientas, no asesoria financiera. La mayoria de quienes hacen day trading pierden dinero, y el apalancamiento del forex lo acelera.
- Ninguna herramienta de este paquete se conecta a un broker ni puede enviar una orden. El usuario pone cada orden a mano.
- Cuenta demo por defecto (`"paper": true`). Pasar a dinero real es decision del usuario, en su propia configuracion.
- Los precios son de Yahoo: indicativos, sin bid ni ask, y pueden ir con retraso. El precio real es el del broker.
- Nunca digas que par operar ni en que direccion. El usuario elige; las herramientas describen y calculan.
- Nunca cambies un limite de `fx/config.json` para que una orden pase.
