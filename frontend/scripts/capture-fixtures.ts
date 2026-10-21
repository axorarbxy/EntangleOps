const base = process.env.EO_API_BASE;
const key = process.env.EO_API_KEY;
if (!base || !key) {
  process.stderr.write(
    'Set EO_API_BASE and EO_API_KEY in the shell environment.\n',
  );
  process.exit(2);
}
const response = await fetch(`${base}/api/v1/me`, {
  headers: { 'X-API-Key': key, Accept: 'application/json' },
  cache: 'no-store',
});
if (!response.ok)
  throw new Error(
    `Backend returned ${response.status} during fixture capture.`,
  );
await response.json();
process.stdout.write(
  'Backend access verified. Use the documented fixture recorder to capture topology and run streams.\n',
);
