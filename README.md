# CasaControl — consola Wi-Fi privada para iPhone

Consola web para gestionar dispositivos de **tu propia red doméstica**. Diseñada para iPhone (Safari → *Añadir a pantalla de inicio*) y para guardar el código en GitHub.

![CasaControl](static/icon.svg)

## ¿Qué funciona?

| Función | Demo (GitHub Pages) | Router MikroTik RouterOS 7 |
|---|---|---|
| Panel adaptable a iPhone | ✅ | ✅ |
| Contraseña de administrador del panel | No necesaria: vista previa pública | ✅ |
| Ver dispositivos | Datos simulados | ✅ DHCP + clientes Wi-Fi reportados por router |
| Buscar, actualizar y filtrar | ✅ | ✅ |
| Bloquear y desbloquear acceso a internet | Simulación | ✅, regla de firewall por MAC |
| Confirmar antes de bloquear | ✅ | ✅ |
| Evitar bloquear el teléfono administrador | Demo protegido | ✅, por su IP DHCP |

**Limitaciones relevantes:**
- El bloqueo de MikroTik restringe tráfico hacia la lista de interfaces `WAN`; **NO expulsa físicamente el equipo del Wi-Fi**. Algunas conexiones FastTrack existentes pueden tardar en detenerse y el equipo puede seguir viendo la red local. **La implementación actual bloquea solo tráfico IPv4**; si IPv6 está activado, el dispositivo podría conservar acceso por IPv6. Para un bloqueo completo hay que adaptar las reglas IPv6 o usar los controles de acceso Wi-Fi del router.
- Algunos dispositivos no aparecen si usan IP estática y no están en una tabla Wi-Fi, o si son clientes de un punto de acceso separado. Las concesiones DHCP **no garantizan** que el dispositivo siga conectado.
- Si el router cambia, también hay que adaptar el conector; no hay API universal entre marcas.
- La **contraseña del Wi-Fi no da permisos administrativos**. Necesitas la cuenta administrativa del router y acceso legítimo a él.

## 1. Probar la interfaz con datos simulados

Puedes subir **todo este proyecto** a un repositorio de GitHub. Activa GitHub Pages: **Settings → Pages → Deploy from a branch → main → /docs**. La web pública solo es una **demostración**, no se conecta al router. No almacena ni pide credenciales reales.

## 2. Ejecutar de verdad en tu red local

**Necesitas:** un ordenador o Raspberry Pi encendido dentro de tu Wi-Fi, Python 3.10+ y un router MikroTik con RouterOS 7 y REST seguro. **GitHub no ejecuta el servidor Python**: solo almacena código y la demostración. En iPhone no basta instalar la web sin un ordenador o un servicio local en marcha.

1. Descarga el ZIP de este repositorio y descomprímelo en un ordenador de tu red.
2. En una terminal, entra en la carpeta, instala dependencias:
   ```bash
   python -m pip install -r requirements.txt
   ```
3. Copia `.env.example` a `.env`; cambia `APP_PASSWORD` por una contraseña **larga, única**, `APP_SECRET` por una cadena aleatoria y `MODE=mikrotik` cuando el router esté preparado. Para experimentar primero, deja `MODE=demo`.
4. Configura en tu router MikroTik (ver documentación oficial de más abajo): la API REST **sobre HTTPS**, con certificado válido o CA confiable, y un usuario específico de acceso local con permisos adecuados. Restringe `www-ssl` y el usuario a la IP del ordenador. **No abras los puertos del router a internet.**
5. Escribe en `.env` los valores reales `ROUTER_URL=https://IP_PRIVADA`, `ROUTER_USER`, `ROUTER_PASSWORD`, `ROUTER_CA_CERT` (ruta al CA de confianza) y `WAN_INTERFACE_LIST` (habitualmente `WAN`). **No desactives la validación TLS.**
6. Inicia:
   ```bash
   python server.py
   ```
7. En el iPhone, conectado a ese mismo Wi-Fi, abre `http://IP_DEL_ORDENADOR:8765` en Safari e inicia sesión con **APP_PASSWORD**. Toca Compartir → **Añadir a pantalla de inicio**.

> Seguridad: La app usa HTTP local por defecto, por lo que la clave de acceso al panel no va cifrada entre iPhone y servidor. Úsala **solo para pruebas en una red privada confiable** y, para uso habitual, configura `TLS_CERT` y `TLS_KEY` con un certificado confiable para el iPhone o colócala detrás de un proxy HTTPS local. La comunicación del servidor con el router está restringida a HTTPS validado. **Jamás publiques `.env`** ni expongas el servidor a internet.

## 3. Uso de los botones

1. Pulsa **Actualizar** para consultar al router.
2. Busca un dispositivo por nombre, MAC o IP.
3. Pulsa **Bloquear internet**, escribe `BLOQUEAR` para confirmar y acepta.
4. Para restaurar, pulsa **Restaurar** y escribe `DESBLOQUEAR`.
5. El backend solo elimina reglas que esta app creó, marcadas con `CASACONTROL_BLOCK:`. No borra reglas ajenas. **Proteger el teléfono se basa en coincidencia de IP y puede ser insuficiente en redes con proxy o IP estática:** configura también su MAC en `PROTECTED_MACS`.

El bloqueo real de IPv4 está condicionado al orden del firewall y a que tu router use la lista de interfaces WAN. Antes de confiar en él, pruébalo con un dispositivo secundario del que tengas permiso; verifica con el router y con el cliente si efectivamente perdió salida a internet.

## Archivos

- `server.py` — backend autenticado, integración RouterOS y confirmación.
- `static/` — interfaz original adaptable a iPhone.
- `docs/` — versión demostrativa independiente para GitHub Pages.
- `.env.example` — plantilla de configuración, **sin contraseñas reales**.
- `tests/test_app.py` — pruebas rápidas de autenticación, confirmación y protección.

## Referencias oficiales

- [REST de MikroTik](https://manual.mikrotik.com/docs/developer-guides/rest-api/)
- [Reglas firewall de MikroTik](https://manual.mikrotik.com/docs/firewall-and-quality-of-service/firewall/filter/)
- [Crear una web app en iPhone con Safari](https://support.apple.com/guide/iphone/open-as-web-app-iphea86e5236/ios)

**Nota:** `MODE=mikrotik` es una implementación preparada para RouterOS, pero no se ha probado contra tu modelo de router. No afirmamos compatibilidad con TP-Link, ZTE, Huawei, Claro o Altice sin conocer el modelo y su API.CasaControl actualizado
