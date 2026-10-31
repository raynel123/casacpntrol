"""CasaControl - consola local para administrar tu red doméstica.

Requiere permisos de administración legítimos del router. Nunca debe exponerse a Internet.
"""
from __future__ import annotations

import hmac
import ipaddress
import os
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, session

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
MODE = os.getenv('MODE', 'demo').lower().strip()
APP_PASSWORD = os.getenv('APP_PASSWORD', '')
APP_SECRET = os.getenv('APP_SECRET', '') or secrets.token_hex(32)
WAN_LIST = os.getenv('WAN_INTERFACE_LIST', 'WAN').strip()
MAC_RE = re.compile(r'^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$')
RULE_PREFIX = 'CASACONTROL_BLOCK:'
PROTECTED_MACS = {v.strip().upper().replace('-', ':') for v in os.getenv('PROTECTED_MACS', '').split(',') if v.strip()}

app = Flask(__name__, static_folder=None)
app.config.update(
    SECRET_KEY=APP_SECRET,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Strict',
    SESSION_COOKIE_SECURE=bool(os.getenv('TLS_CERT') and os.getenv('TLS_KEY')),
    MAX_CONTENT_LENGTH=10 * 1024,
    JSON_SORT_KEYS=False,
)

LOGIN_ATTEMPTS = defaultdict(list)

DEMO_DEVICES = [
    {'mac': '02:11:22:33:44:51', 'name': 'iPhone de casa', 'ip': '192.168.88.24', 'connection': 'Wi-Fi confirmado', 'online': True, 'protected': True, 'blocked': False},
    {'mac': '02:11:22:33:44:52', 'name': 'Smart TV', 'ip': '192.168.88.31', 'connection': 'Wi-Fi confirmado', 'online': True, 'protected': False, 'blocked': False},
    {'mac': '02:11:22:33:44:53', 'name': 'Laptop', 'ip': '192.168.88.42', 'connection': 'DHCP · conexión no confirmada', 'online': False, 'protected': False, 'blocked': False},
    {'mac': '02:11:22:33:44:54', 'name': 'Teléfono invitado', 'ip': '192.168.88.57', 'connection': 'Wi-Fi confirmado', 'online': True, 'protected': False, 'blocked': False},
    {'mac': '02:11:22:33:44:55', 'name': 'Consola de juegos', 'ip': '192.168.88.70', 'connection': 'Wi-Fi confirmado', 'online': True, 'protected': False, 'blocked': False},
]


def normalized_mac(value):
    mac = str(value or '').strip().upper().replace('-', ':')
    if not MAC_RE.fullmatch(mac):
        raise ValueError('Dirección MAC inválida.')
    return mac


def login_required():
    return session.get('authenticated') is True


def json_error(message, status=400):
    return jsonify(error=message), status


class RouterError(Exception):
    pass


class MikroTik:
    def __init__(self):
        self.base = os.getenv('ROUTER_URL', '').rstrip('/')
        self.user = os.getenv('ROUTER_USER', '')
        self.password = os.getenv('ROUTER_PASSWORD', '')
        ca_cert = os.getenv('ROUTER_CA_CERT', '').strip()
        self.verify = str((ROOT / ca_cert).resolve()) if ca_cert and not os.path.isabs(ca_cert) else (ca_cert or True)
        if not self.base.startswith('https://') or not self.user or not self.password:
            raise RouterError('Configura ROUTER_URL (https), ROUTER_USER y ROUTER_PASSWORD en .env.')
        if self.base.endswith('/rest'):
            self.base = self.base[:-5]
        # Impedir URL externas o extrañas por configuración accidental.
        from urllib.parse import urlsplit
        parsed = urlsplit(self.base)
        try:
            addr = ipaddress.ip_address(parsed.hostname or '')
            if not addr.is_private:
                raise ValueError()
        except ValueError:
            raise RouterError('ROUTER_URL debe usar una IP privada de tu red (por ejemplo 192.168.88.1).')
        self.http = requests.Session()
        self.http.auth = (self.user, self.password)
        self.http.verify = self.verify
        self.http.headers.update({'Accept': 'application/json'})

    def req(self, method, path, **kwargs):
        try:
            resp = self.http.request(method, self.base + '/rest/' + path, timeout=8, **kwargs)
            resp.raise_for_status()
            return resp.json() if resp.content else []
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                raise RouterError('Usuario o contraseña del router incorrectos.') from exc
            if exc.response is not None and exc.response.status_code in (403, 404):
                raise RouterError('El router no permite esta operación. Revisa el acceso REST y los permisos.') from exc
            raise RouterError('El router rechazó la petición: ' + str(exc)) from exc
        except requests.RequestException as exc:
            raise RouterError('No se pudo conectar al router: ' + str(exc)) from exc
        except ValueError as exc:
            raise RouterError('El router devolvió una respuesta inválida.') from exc

    def optional_get(self, path):
        try:
            return self.req('GET', path)
        except RouterError:
            return []

    def rules(self):
        return self.req('GET', 'ip/firewall/filter')

    def devices(self, client_ip):
        leases = self.req('GET', 'ip/dhcp-server/lease')
        wifi_new = self.optional_get('interface/wifi/registration-table')
        wifi_old = self.optional_get('interface/wireless/registration-table')
        blocked_rules = {r.get('comment', '').removeprefix(RULE_PREFIX): r for r in self.rules() if r.get('comment', '').startswith(RULE_PREFIX) and r.get('disabled') != 'true'}
        found = {}
        for lease in leases:
            try:
                mac = normalized_mac(lease.get('active-mac-address') or lease.get('mac-address'))
            except ValueError:
                continue
            ip = lease.get('active-address') or lease.get('address') or ''
            name = lease.get('host-name') or lease.get('comment') or ('Dispositivo ' + mac[-5:])
            found[mac] = {'mac': mac, 'name': name, 'ip': ip, 'connection': 'DHCP · conexión no confirmada', 'online': False}
        for record in [*wifi_new, *wifi_old]:
            try:
                mac = normalized_mac(record.get('mac-address'))
            except ValueError:
                continue
            existing = found.setdefault(mac, {'mac': mac, 'name': 'Dispositivo ' + mac[-5:], 'ip': '', 'connection': '', 'online': False})
            existing['connection'] = 'Wi-Fi confirmado'
            existing['online'] = True
        for mac, device in found.items():
            device['blocked'] = mac in blocked_rules
            device['protected'] = (mac in PROTECTED_MACS or bool(device['ip'] and device['ip'] == client_ip))
        return sorted(found.values(), key=lambda d: (not d['online'], d['name'].lower()))

    def block(self, mac):
        rules = self.rules()
        if any(r.get('comment') == RULE_PREFIX + mac for r in rules):
            raise RouterError('Este dispositivo ya tiene una regla de CasaControl.')
        lists = self.req('GET', 'interface/list')
        if WAN_LIST not in {x.get('name') for x in lists}:
            raise RouterError('No existe la lista de interfaz WAN configurada. Compruébala antes de bloquear.')
        payload = {
            'chain': 'forward', 'action': 'drop', 'src-mac-address': mac,
            'out-interface-list': WAN_LIST,
            'comment': RULE_PREFIX + mac,
        }
        first_forward = next((r.get('.id') for r in rules if r.get('chain') == 'forward' and not r.get('dynamic') == 'true'), None)
        if first_forward:
            payload['place-before'] = first_forward
        created = self.req('PUT', 'ip/firewall/filter', json=payload)
        if not isinstance(created, dict) or not created.get('.id'):
            raise RouterError('No se confirmó la creación de la regla del firewall.')

    def unblock(self, mac):
        matched = [r for r in self.rules() if r.get('comment') == RULE_PREFIX + mac]
        if not matched:
            raise RouterError('No hay ningún bloqueo creado por CasaControl para este dispositivo.')
        for rule in matched:
            self.req('DELETE', 'ip/firewall/filter/' + rule['.id'])


def get_devices():
    if MODE == 'demo':
        return [dict(x) for x in DEMO_DEVICES]
    if MODE == 'mikrotik':
        return MikroTik().devices(request.remote_addr)
    raise RouterError('MODE no reconocido. Usa demo o mikrotik.')


def require_action():
    if not login_required():
        return json_error('Inicia sesión.', 401)
    token = request.headers.get('X-CSRF-Token', '')
    if not token or not hmac.compare_digest(token, session.get('csrf', '')):
        return json_error('Token de seguridad inválido.', 403)
    return None


@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    return response


@app.get('/')
def index():
    return send_from_directory(ROOT / 'static', 'index.html')


@app.get('/<path:filename>')
def static_files(filename):
    if filename not in {'style.css', 'app.js', 'manifest.webmanifest', 'icon.svg', 'icon-apple.png'}:
        return json_error('No encontrado.', 404)
    return send_from_directory(ROOT / 'static', filename)


@app.get('/api/session')
def current_session():
    return jsonify(authenticated=login_required(), mode=MODE,
                   csrf=session.get('csrf', '') if login_required() else '')


@app.post('/api/login')
def login():
    if not APP_PASSWORD:
        return json_error('Primero configura APP_PASSWORD en el archivo .env.', 503)
    ip = request.remote_addr or 'unknown'
    now = time.monotonic()
    recent = [t for t in LOGIN_ATTEMPTS[ip] if now - t < 90]
    LOGIN_ATTEMPTS[ip] = recent
    if len(recent) >= 7:
        return json_error('Demasiados intentos. Inténtalo más adelante.', 429)
    obj = request.get_json(silent=True) or {}
    if not hmac.compare_digest(str(obj.get('password', '')).encode(), APP_PASSWORD.encode()):
        LOGIN_ATTEMPTS[ip].append(now)
        return json_error('Contraseña incorrecta.', 401)
    LOGIN_ATTEMPTS.pop(ip, None)
    session.clear()
    session['authenticated'] = True
    session['csrf'] = secrets.token_urlsafe(32)
    session.permanent = False
    return jsonify(ok=True, mode=MODE, csrf=session['csrf'])


@app.post('/api/logout')
def logout():
    check = require_action()
    if check:
        return check
    session.clear()
    return jsonify(ok=True)


@app.get('/api/devices')
def devices():
    if not login_required():
        return json_error('Inicia sesión.', 401)
    try:
        items = get_devices()
        return jsonify(devices=items, mode=MODE, simulated=MODE == 'demo',
                       timestamp=datetime.now(timezone.utc).isoformat())
    except RouterError as exc:
        return json_error(str(exc), 502)


def toggle_device(blocking):
    check = require_action()
    if check:
        return check
    data = request.get_json(silent=True) or {}
    try:
        mac = normalized_mac(data.get('mac'))
        if data.get('confirm') != ('BLOQUEAR' if blocking else 'DESBLOQUEAR'):
            return json_error('Debes confirmar expresamente esta acción.')
        items = get_devices()
        device = next((d for d in items if d['mac'] == mac), None)
        if not device:
            return json_error('Dispositivo no encontrado. Actualiza la lista.', 404)
        if device['protected'] and blocking:
            return json_error('Este dispositivo está protegido para evitar perder el acceso.', 409)
        if MODE == 'demo':
            for row in DEMO_DEVICES:
                if row['mac'] == mac:
                    row['blocked'] = blocking
        elif MODE == 'mikrotik':
            adapter = MikroTik()
            if blocking:
                adapter.block(mac)
            else:
                adapter.unblock(mac)
        return jsonify(ok=True, message=('Internet bloqueado' if blocking else 'Acceso restaurado'), simulated=MODE == 'demo')
    except (RouterError, ValueError) as exc:
        return json_error(str(exc), 400)


@app.post('/api/block')
def block_device():
    return toggle_device(True)


@app.post('/api/unblock')
def unblock_device():
    return toggle_device(False)


if __name__ == '__main__':
    if not APP_PASSWORD:
        raise SystemExit('Configura APP_PASSWORD en .env antes de iniciar.')
    if MODE not in {'demo', 'mikrotik'}:
        raise SystemExit('MODE debe ser demo o mikrotik.')
    if not os.getenv('APP_SECRET'):
        print('Aviso: APP_SECRET no definido: las sesiones se perderán al reiniciar.')
    if not os.getenv('TLS_CERT'):
        print('Aviso: usando HTTP. Úsalo solo en una red doméstica privada; configura HTTPS para proteger la sesión.')
    tls_cert, tls_key = os.getenv('TLS_CERT'), os.getenv('TLS_KEY')
    cert = (tls_cert, tls_key) if tls_cert and tls_key else None
    app.run(host=os.getenv('APP_HOST', '0.0.0.0'), port=int(os.getenv('APP_PORT', '8765')),
            debug=False, ssl_context=cert, threaded=True)
