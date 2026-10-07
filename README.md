# Compra Hub para Home Assistant

Integración de Home Assistant para el hub familiar [compra.raspimc.org](https://raspimc.org/hub/): la lista de la compra, las tareas, el calendario, los gastos y el menú, dentro de Home Assistant.

Cada persona conecta su propia cuenta del hub y ve lo mismo que en la app: lo personal y lo de sus grupos.

## Qué aparece en Home Assistant

| Entidad | Qué hace |
|---|---|
| **Compra** y **Compra ‹grupo›** (listas de tareas) | Tu lista de la compra y la de cada grupo. Puedes añadir, tachar, renombrar y borrar productos. La cantidad va en la descripción. «Eliminar completados» desmarca los productos fijos (📌) en vez de borrarlos, igual que «Vaciar comprados» en la app. |
| **Tareas** y **Tareas ‹grupo›** (listas de tareas) | Añadir, completar o reabrir, poner fecha y borrar. «Haciendo» cuenta como pendiente. |
| **Calendario** y **Calendario ‹grupo›** | Los recordatorios del hub, incluidos los que se repiten. Solo lectura. |
| **Gastos Este mes** | Lo que llevas gastado este mes (gastos personales). |
| **Gastos Saldo ‹grupo›** | Tu saldo en cada grupo: positivo, te deben; negativo, debes. El atributo `situacion` lo dice con palabras. |
| **Menú Comida de hoy** y **Menú Cena de hoy** (y por grupo) | El plato planificado para hoy, o «Sin planificar». |

Los datos se actualizan cada minuto. Lo que cambias desde Home Assistant se ve al momento. Si entras o sales de un grupo, sus entidades aparecen o desaparecen solas.

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

## Voz (Assist)

Funcionan frases como:

- «añade leche a la lista compra»
- «añade sal a la lista compra casa» (lista del grupo «Casa»)
- «añade llamar al banco a la lista de tareas»
- «quita leche de la lista compra»

**«…a la lista de la compra»** va siempre a la lista de la compra propia de Home Assistant, que viene activada de serie. Esa frase tiene prioridad y una integración no la puede cambiar. Si no usas esa lista, quita la integración «Lista de la compra» en Ajustes y la frase llegará a la del hub.

## Privacidad

La integración solo habla con `compra.raspimc.org` (los datos) y con `keycloak.raspimc.org` (el inicio de sesión). No envía nada a terceros. El token se guarda en tu Home Assistant como el de cualquier otra integración.

## Licencia

[PolyForm Strict 1.0.0](LICENSE): uso no comercial, sin modificaciones ni redistribución.
