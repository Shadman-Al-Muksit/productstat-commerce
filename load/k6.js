import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const auth = JSON.parse(open(__ENV.AUTH_FILE || '../.runtime/load-auth.json'));
const base = __ENV.BASE_URL || 'http://127.0.0.1:8002';
const catalog = new Trend('catalog_ms', true);
const analytics = new Trend('analytics_ms', true);
export const options = {
  scenarios: {
    browsers: {executor: 'constant-vus', vus: 20, duration: __ENV.DURATION || '30s', exec: 'browse'},
    staff: {executor: 'constant-vus', vus: 5, duration: __ENV.DURATION || '30s', exec: 'report'},
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate==1'],
    catalog_ms: ['p(95)<1000'],
    analytics_ms: ['p(95)<2000'],
  },
};
function get(path, session) {
  return http.get(base + '/api/v1/' + path, {headers: {
    Cookie: 'sessionid=' + session,
    'X-Forwarded-Proto': 'https',
  }});
}
export function browse() {
  const response = get('catalog/products/?page_size=24&page=' + ((__ITER % 4) + 1), auth.customer);
  catalog.add(response.timings.duration);
  check(response, {'catalog successful': r => r.status === 200 && r.json('results').length > 0});
  sleep(1);
}
export function report() {
  const range = __ITER % 5 === 0 ? '?start=' + auth.start + '&end=' + auth.end : '';
  const response = get('analytics/' + range, auth.analyst);
  analytics.add(response.timings.duration);
  check(response, {'report successful': r => r.status === 200 && r.json('summary.orders') >= 0});
  sleep(1);
}
export function handleSummary(data) {
  return {
    [__ENV.RESULT_FILE || '../.runtime/k6-summary.json']: JSON.stringify(data, null, 2),
    stdout: JSON.stringify({catalog_ms: data.metrics.catalog_ms.values,
      analytics_ms: data.metrics.analytics_ms.values,
      requests: data.metrics.http_reqs.values,
      failed: data.metrics.http_req_failed.values, checks: data.metrics.checks.values}, null, 2) + '\n',
  };
}
