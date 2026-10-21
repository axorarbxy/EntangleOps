export const MAX_STEPS = 5760,
  MAX_EXPECTED_REQUESTS = 20000;
export const nSteps = (hours: number, dt: number) =>
  Math.floor((hours * 3600) / dt);
export const expectedRequests = (rate: number, hours: number, dt: number) =>
  rate * nSteps(hours, dt) * (dt / 60);
