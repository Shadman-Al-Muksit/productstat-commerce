"""Exercise the deployed Compose HTTPS path using synthetic data only."""
import argparse
import datetime as dt
import http.cookiejar
import html
import json
import re
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base', default='https://localhost')
parser.add_argument('--allow-self-signed', action='store_true', help='For the disposable localhost CI certificate only.')
args = parser.parse_args()
if args.allow_self_signed and args.base != 'https://localhost':
    raise SystemExit('Self-signed bypass is restricted to https://localhost CI.')
context = ssl._create_unverified_context() if args.allow_self_signed else ssl.create_default_context()
values = dict(line.split('=', 1) for line in (ROOT / '.env.production').read_text().splitlines() if line and not line.startswith('#'))

class Client:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = ''
    def call(self, method, path, data=None, headers=None, expected=200):
        extra = {'Origin': args.base, 'Referer': args.base + '/', **(headers or {})}
        if method != 'GET':
            self.csrf = self.call('GET', 'bootstrap/')['csrfToken']
            extra['X-CSRFToken'] = self.csrf
        if data is not None:
            extra['Content-Type'] = 'application/json'
        request = urllib.request.Request(args.base + '/api/v1/' + path,
                                        data=json.dumps(data).encode() if data is not None else None,
                                        method=method, headers=extra)
        try:
            response = self.opener.open(request, timeout=30)
        except urllib.error.HTTPError as exc:
            if exc.code == expected:
                return None
            raise RuntimeError(f'{method} {path.split("?")[0]} returned {exc.code}; expected {expected}') from exc
        with response:
            if response.status != expected:
                raise RuntimeError(f'{method} {path.split("?")[0]} returned {response.status}; expected {expected}')
            return json.load(response)

started = time.monotonic()
guest, staff = Client(), Client()
for attempt in range(60):
    try:
        assert guest.call('GET', 'health/')['status'] == 'ok'
        with urllib.request.urlopen(args.base + '/', context=context, timeout=10) as response:
            assert response.status == 200
            page_html = response.read().decode()
        break
    except (urllib.error.URLError, AssertionError):
        if attempt == 59:
            raise
        time.sleep(1)
assets = re.findall(r'<script[^>]+src="([^"]+)"', page_html)
asset = next(asset for asset in assets if asset.startswith('/_next/static/'))
with urllib.request.urlopen(args.base + html.unescape(asset), context=context, timeout=20) as response:
    assert response.status == 200 and len(response.read()) > 0
bootstrap = guest.call('GET', 'bootstrap/')
catalogue = guest.call('GET', 'catalog/products/')
product = next(product for product in catalogue['results'] if any(sku['available'] >= 2 for sku in product['skus']))
sku = next(sku for sku in product['skus'] if sku['available'] >= 2)
with urllib.request.urlopen(args.base + product['image_url'], context=context, timeout=20) as response:
    assert response.status == 200 and b'<svg' in response.read()
with urllib.request.urlopen(args.base + '/products/' + product['slug'], context=context, timeout=20) as response:
    assert response.status == 200 and html.escape(product['name']) in response.read().decode()
staff.call('POST', 'auth/login/', {'username': 'administrator', 'password': values['DEMO_PASSWORD']})
date = dt.datetime.now(dt.timezone(dt.timedelta(hours=6))).date().isoformat()
report = f'analytics/?start={date}&end={date}&product_ids={product["id"]}'
before = staff.call('GET', report)
guest.call('POST', 'cart/', {'sku_id': sku['id'], 'quantity': 2})
result = guest.call('POST', 'checkout/', {'customer_name': 'Synthetic CI customer', 'phone': '01700000000', 'email': '',
    'address': {'line1': 'Synthetic CI address', 'city': 'Chattogram'},
    'delivery_zone_id': bootstrap['delivery_zones'][0]['id'], 'payment_method': 'cod'},
    headers={'Idempotency-Key': 'container-' + uuid.uuid4().hex}, expected=201)
order = result['order']
assert order['status'] == 'confirmed'
guest.call('GET', f'orders/{order["id"]}/', expected=403)
route = f'staff/orders/{order["id"]}/action/'
for action in [{'action':'prepare'}, {'action':'dispatch', 'carrier':'Synthetic CI courier', 'tracking_number':'CI-' + order['number']},
               {'action':'deliver'}, {'action':'collect_cod', 'amount':order['grand_total'], 'reference':'Synthetic CI receipt'},
               {'action':'settle_cod', 'amount':order['grand_total'], 'reference':'Synthetic CI settlement'}]:
    staff.call('POST', route, action)
returned = guest.call('POST', f'orders/{order["id"]}/returns/?token={result["access_token"]}',
                      {'reason':'Synthetic CI inspection', 'lines':[{'order_line_id':order['lines'][0]['id'], 'quantity':1}]}, expected=201)
return_route = f'staff/returns/{returned["id"]}/action/'
staff.call('POST', return_route, {'action':'approve'})
staff.call('POST', return_route, {'action':'receive'})
staff.call('POST', return_route, {'action':'inspect', 'lines':[{'id':returned['lines'][0]['id'], 'accepted_quantity':1, 'restock_quantity':1, 'disposition':'restock'}]})
updated = staff.call('GET', f'staff/orders/{order["id"]}/')
staff.call('POST', f'staff/refunds/{updated["refunds"][0]["id"]}/confirm/', {'reference':'Synthetic CI verified refund'})
after = staff.call('GET', report)
assert after['summary']['delivered_units'] - before['summary']['delivered_units'] == 2
assert after['summary']['returned_units'] - before['summary']['returned_units'] == 1
evidence = {'status':'passed', 'transport':'Caddy HTTPS (local CI self-signed)' if args.allow_self_signed else 'Verified HTTPS',
            'standalone_frontend':True, 'static_asset':True, 'product_image':True, 'product_metadata':True,
            'order_number':order['number'], 'workflow':'purchase/prepare/dispatch/deliver/COD collection/settlement/partial return/refund/report',
            'elapsed_seconds':round(time.monotonic()-started, 2)}
(ROOT / '.runtime').mkdir(exist_ok=True)
(ROOT / '.runtime' / 'container-evidence.json').write_text(json.dumps(evidence, indent=2))
print(json.dumps(evidence, indent=2))
