export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
    public retryAfterS?: number,
    public fields?: { loc: (string | number)[]; msg: string }[],
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
