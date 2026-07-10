import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 200  },
    { duration: '1m',  target: 500  },
    { duration: '1m',  target: 1000 },
    { duration: '30s', target: 0    },
  ],
  thresholds: {
    http_req_duration: ['p(95)<5000'],
    http_req_failed:   ['rate<0.5'],
  },
};

export default function () {
  const res = http.get('https://jolly-term-bf1a.jwbaik2.workers.dev/');
  check(res, {
    'status 200': (r) => r.status === 200,
    'response time < 1s': (r) => r.timings.duration < 1000,
  });
  sleep(1);
}
