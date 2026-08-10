// The configured Axios instance every service module (authApi, chatApi,
// messageApi) uses. Two interceptors do all the auth work so calling code
// never has to think about tokens:
//
//   - request:  attach the current access token, if we have one.
//   - response: on a 401 (and only once per request), silently refresh and
//               retry - so a request made right as the access token expires
//               just works instead of surfacing an error to the caller.
//
// withCredentials is required globally, not just on auth endpoints: it's
// what makes the browser send the HTTP-only refresh cookie at all.
import axios, { AxiosHeaders, type InternalAxiosRequestConfig } from 'axios';

import { refreshAccessToken } from './authRefresh';
import { getAuthState } from './authStore';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  withCredentials: true,
});

apiClient.interceptors.request.use((config) => {
  const { accessToken } = getAuthState();
  if (accessToken) {
    config.headers.set('Authorization', `Bearer ${accessToken}`);
  }
  return config;
});

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as RetryableConfig | undefined;

    // /auth/refresh itself must never trigger this dance - it would recurse
    // forever if the refresh call itself came back 401.
    const isRefreshCall = originalRequest?.url?.includes('/auth/refresh');

    if (error.response?.status === 401 && originalRequest && !originalRequest._retried && !isRefreshCall) {
      originalRequest._retried = true;
      const newToken = await refreshAccessToken();
      if (newToken) {
        originalRequest.headers = AxiosHeaders.from(originalRequest.headers);
        originalRequest.headers.set('Authorization', `Bearer ${newToken}`);
        return apiClient(originalRequest);
      }
    }

    return Promise.reject(error);
  },
);

export default apiClient;
