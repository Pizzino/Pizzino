---
name: fx-alerts
description: >-
  Alertas de forex. Suena cuando un par toca un nivel, el stop o el objetivo, o cuando llega una hora. Convierte
  el plan en tres alertas de una vez (stop, objetivo y hora de cierre antes del rollover), cada una suena una
  sola vez, y revisa las velas desde que se creo la alerta para no perderse un toque. Usar cuando el usuario
  diga "avisame si el EURUSD llega a", "vigila mi stop", "vigila mi operacion", "recuerdame cerrar a las
  16:30", "alert me when", "watch my trade", o justo despues de anotar una operacion con /fx-ticket.
argument-hint: "[add --from-plan | add PAR above|below PRECIO | check | list]"
---

# fx-alerts

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --from-plan            # stop, objetivo y hora de cierre de fx/plan.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add EURUSD above 1.1080    # o below
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --time 16:30 --label "cerrar todo"    # hora de Nueva York
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check                      # suena lo que se toco, una sola vez
python3 "${CLAUDE_SKILL_DIR}/alerts.py" list
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clear
```

## Como funciona

- `check` baja las velas de 5 minutos del par y mira todas las que hay desde que se creo la alerta: si
  alguna toco el nivel, suena aunque el precio ya haya vuelto. Codigo 0 si algo sono.
- Cada alerta suena una vez y queda marcada en `fx/alerts.json`.
- Para vigilar seguido hay que repetir `check` cada pocos minutos (por ejemplo `/loop 5m` con este comando).
  Sin eso, nadie esta mirando.

## Limites

- Precios de Yahoo, indicativos y con posible retraso. El stop de verdad es el que el usuario puso en su
  broker; esta alerta solo avisa.
- Una vela de 5 minutos puede tocar el stop y el objetivo: si suenan los dos en la misma revision, el
  resultado real lo dice el broker.

## Pasos

1. Tras `/fx-ticket opened`: `alerts.py add --from-plan`. Di las tres alertas.
2. Corre `check` cuando el usuario pregunte, o programalo si lo pide.
3. Cuando suena el stop o el objetivo, di que confirme en su broker y que anote el cierre con `/fx-ticket close`.
4. Cuando suena la hora de cierre, di que cierre la posicion a mano si sigue abierta.

La cadena completa: `/fx-scanner` -> `/fx-calendar` -> `/fx-entry` -> `/fx-exit` -> `/fx-timemachine` -> `/fx-budget` -> `/fx-risk` -> `/fx-ticket`, y `/fx-alerts` mientras la operacion esta abierta.
Cada skill deja su archivo en la carpeta `fx/` del proyecto y la siguiente lo lee. `${CLAUDE_SKILL_DIR}` es la carpeta de esta skill.

## Seguridad

- Educacion y herramientas, no asesoria financiera. La mayoria de quienes hacen day trading pierden dinero, y el apalancamiento del forex lo acelera.
- Ninguna herramienta de este paquete se conecta a un broker ni puede enviar una orden. El usuario pone cada orden a mano.
- Cuenta demo por defecto (`"paper": true`). Pasar a dinero real es decision del usuario, en su propia configuracion.
- Los precios son de Yahoo: indicativos, sin bid ni ask, y pueden ir con retraso. El precio real es el del broker.
- Nunca digas que par operar ni en que direccion. El usuario elige; las herramientas describen y calculan.
- Nunca cambies un limite de `fx/config.json` para que una orden pase.
