# Changelog

## Frontend integration

- Added the React console, typed API integration, replay, monitoring and security/admin surfaces, demo mode, and Caddy/Docker wiring.
- Added `style-src-attr 'unsafe-inline'` to Caddy's Content Security Policy because Recharts' `ResponsiveContainer` sets its sizing through inline style attributes. `style-src` remains `'self'`; script policy remains `'self'`.
- `npm audit --audit-level=high` could not be completed in this environment because the npm registry was unreachable (`ENOTFOUND`). An attempted network-enabled retry was rejected by automatic review because it would send dependency metadata to the registry. No audit pass is claimed.
