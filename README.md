# Compra Hub para Home Assistant

Integración de Home Assistant para el hub familiar [compra.raspimc.org](https://raspimc.org/hub/): la lista de la compra, las tareas, el calendario, los gastos y el menú, dentro de Home Assistant.

Cada persona conecta su propia cuenta del hub y ve lo mismo que en la app: lo personal y lo de sus grupos.

## Qué aparece en Home Assistant

| Entidad | Qué hace |
|---|---|
| **Compra** y **Compra ‹grupo›** (listas de tareas) | Tu lista de la compra y la de cada grupo. «Compra» aparece siempre: si aún no has abierto la lista de la compra en la app, se crea «Mi lista» al añadir el primer producto. Si tienes varias listas personales, sale una por lista («Compra ‹lista›»). Puedes añadir, tachar, renombrar y borrar productos. La cantidad va en la descripción. «Eliminar completados» desmarca los productos fijos (📌) en vez de borrarlos, igual que «Vaciar comprados» en la app. |
| **Tareas** y **Tareas ‹grupo›** (listas de tareas) | Añadir, completar o reabrir, poner fecha y borrar. «Haciendo» cuenta como pendiente. |
| **Calendario** y **Calendario ‹grupo›** | Los recordatorios del hub, incluidos los que se repiten. Se pueden crear, cambiar y borrar desde Home Assistant (repetición diaria, semanal o mensual, como en la app). |
| **Tareas Para hoy** | Cuántas tareas vencen hoy o van con retraso. El atributo `tareas` las lista. |
| **Gastos Deudas ‹grupo›** | Cuántas deudas quedan en el grupo. Los atributos `resumen` y `deudas` dicen quién debe a quién. |
| **Gastos Este mes** | Lo que llevas gastado este mes (gastos personales). |
| **Gastos Saldo ‹grupo›** | Tu saldo en cada grupo: positivo, te deben; negativo, debes. El atributo `situacion` lo dice con palabras. |
| **Menú Comida de hoy** y **Menú Cena de hoy** (y por grupo) | El plato planificado para hoy, o «Sin planificar». |

| **Compra Hub** (panel en la barra lateral) | El hub completo dentro de Home Assistant, con un botón «Abrir en una ventana». Se puede ocultar en las opciones de la integración. |

Los datos se actualizan cada minuto. Lo que cambias desde Home Assistant se ve al momento. Si entras o sales de un grupo, sus entidades aparecen o desaparecen solas.

## Tarjeta para la pantalla principal

La integración trae la tarjeta **Compra Hub**. Aparece sola en el selector de tarjetas al editar un panel, sin añadir recursos a mano. Tiene tres pestañas:

- **Compra:** tus listas y las de tus grupos. Puedes añadir con cantidad, tachar y quitar los tachados, y se actualiza en directo.
- **Hoy:** las tareas que vencen (se pueden completar desde aquí), los recordatorios del día y el menú de hoy.
- **Gastos:** lo gastado este mes, tu saldo y quién debe a quién en cada grupo, y un formulario para apuntar un gasto.

```yaml
type: custom:compra-hub-card
# Opcional:
# tab: hoy          # pestaña inicial: compra, hoy o gastos
# entry_id: …       # cuenta concreta; por defecto, la del usuario que mira el panel
```

## Acciones

Para automatizaciones y scripts:

- `compra_hub.add_expense`: apunta un gasto, personal o de un grupo. Admite quién pagó y entre quién se reparte.
- `compra_hub.plan_meal`: pone un plato en el menú, la comida o la cena de un día.
- `compra_hub.settle_debts`: marca como pagado todo lo pendiente entre tú y otra persona de un grupo.

Las tres devuelven datos si se piden (`response_variable`). Si hay varias cuentas conectadas, usan la del usuario de Home Assistant vinculado en las opciones de la integración, o la que indiques con `config_entry_id`.

## Instalación

### Con HACS

1. HACS → menú ⋮ → **Repositorios personalizados**.
2. Repositorio: `https://github.com/ElPostilla/ha-compra-hub`, tipo **Integración**.
3. Busca «Compra Hub (raspimc)», descárgala y reinicia Home Assistant.

### A mano

Copia `custom_components/compra_hub` en la carpeta `custom_components` de tu configuración de Home Assistant y reinicia.

## Configuración

1. **Ajustes → Dispositivos y servicios → Añadir integración → «Compra Hub (raspimc)»**.
2. Deja el hub en `compra.raspimc.org`.
3. Inicia sesión con tu cuenta del hub. Al volver, la página de **my.home-assistant.io** te pide una vez la dirección de tu Home Assistant: escríbela y continúa.

No hace falta crear credenciales ni copiar claves. Home Assistant renueva solo la sesión, que no caduca mientras se use al menos una vez cada 30 días. Si cierras la sesión desde tu cuenta del hub, Home Assistant te pedirá volver a entrar.

## El hub dentro de Home Assistant

La integración añade a la barra lateral el panel **Compra Hub**, con la app del hub dentro. La sesión es la del propio hub, independiente de la de Home Assistant: la primera vez inicias sesión dentro del panel.

Por seguridad, el hub solo se deja mostrar dentro de otra web si esa web está en su mismo dominio y su servidor de inicio de sesión la tiene permitida. Hoy está permitida `homeassistant.raspimc.org`. En cualquier otro Home Assistant, el panel puede quedarse en blanco o pedir la sesión una y otra vez, sobre todo en el iPhone, que bloquea las cookies de otros dominios dentro de una página. En ese caso, usa el botón **Abrir en una ventana** del propio panel, que abre el hub aparte (en la app del móvil, en su navegador integrado). Si no quieres el panel, desactívalo en **Ajustes → Dispositivos y servicios → Compra Hub → Configurar**.

## Voz (Assist)

**Listas:**

- «añade leche a la lista compra»
- «añade sal a la lista compra casa» (lista del grupo «Casa»)
- «añade llamar al banco a la lista de tareas»
- «quita leche de la lista compra»

**Gastos, menú y cuentas:**

- «apunta un gasto de 12,50 euros en el súper», «he gastado veinte con cincuenta en gasolina»
- «apunta en casa un gasto de 30 euros en la compra» (a partes iguales en el grupo «Casa»)
- «cuánto he gastado este mes»
- «cuánto debo», «quién me debe», «quién debe a quién en casa»
- «ya he pagado a ana en casa» (salda lo pendiente entre los dos)
- «qué hay de cenar», «qué comemos mañana»
- «pon lentejas para comer mañana», «pon tortilla para cenar hoy en casa»

Los importes se entienden en cifras y en palabras. La categoría del gasto se deduce del concepto (súper → comida, gasolina → transporte…). Con varias cuentas conectadas, Assist usa la del usuario de Home Assistant que habla: vincúlalo en **Configurar** de la integración.

**«…a la lista de la compra»** va siempre a la lista de la compra propia de Home Assistant, que viene activada de serie. Esa frase tiene prioridad y una integración no la puede cambiar. Si no usas esa lista, quita la integración «Lista de la compra» en Ajustes y la frase llegará a la del hub.

## Privacidad

La integración solo habla con `compra.raspimc.org` (los datos) y con `keycloak.raspimc.org` (el inicio de sesión). No envía nada a terceros. El token se guarda en tu Home Assistant como el de cualquier otra integración.

## Licencia

[PolyForm Strict 1.0.0](LICENSE): uso no comercial, sin modificaciones ni redistribución.
