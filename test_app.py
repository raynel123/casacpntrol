import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ['MODE'] = 'demo'
os.environ['APP_PASSWORD'] = 'prueba-segura'
os.environ['APP_SECRET'] = 'test-secret-only'
from server import app


def test_auth_and_protection():
    c = app.test_client()
    assert c.get('/api/devices').status_code == 401
    assert c.post('/api/login', json={'password':'incorrecta'}).status_code == 401
    login = c.post('/api/login', json={'password':'prueba-segura'})
    assert login.status_code == 200
    csrf = login.get_json()['csrf']
    headers = {'X-CSRF-Token': csrf}
    result = c.get('/api/devices')
    assert result.status_code == 200
    items = result.get_json()['devices']
    first = items[0]['mac']
    assert c.post('/api/block', json={'mac':items[1]['mac'], 'confirm':'BLOQUEAR'}).status_code == 403
    assert c.post('/api/block', headers=headers, json={'mac':first,'confirm':'BLOQUEAR'}).status_code == 409
    mac = items[1]['mac']
    assert c.post('/api/block', headers=headers, json={'mac':mac,'confirm':'NO'}).status_code == 400
    assert c.post('/api/block', headers=headers, json={'mac':mac,'confirm':'BLOQUEAR'}).status_code == 200
    assert next(x for x in c.get('/api/devices').get_json()['devices'] if x['mac']==mac)['blocked']
    assert c.post('/api/unblock', headers=headers, json={'mac':mac,'confirm':'DESBLOQUEAR'}).status_code == 200
    assert not next(x for x in c.get('/api/devices').get_json()['devices'] if x['mac']==mac)['blocked']
    assert c.post('/api/logout', headers=headers, json={}).status_code == 200
    assert c.get('/api/devices').status_code == 401
