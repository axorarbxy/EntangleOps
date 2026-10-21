import { QueryClient } from '@tanstack/react-query';
import { ApiError } from './api/errors';
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      refetchOnWindowFocus: true,
      retry: (count, error) => {
        if (count >= 2) return false;
        if (error instanceof ApiError) {
          if ([401, 403, 404, 409, 422].includes(error.status)) return false;
          if ([429, 503].includes(error.status)) return true;
          return error.status === 0;
        }
        return false;
      },
      retryDelay: (attempt, error) =>
        error instanceof ApiError && error.retryAfterS
          ? error.retryAfterS * 1000
          : [1000, 3000][Math.min(attempt, 1)],
    },
    mutations: { retry: false },
  },
});
