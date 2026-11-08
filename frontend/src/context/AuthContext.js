import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

// In production, use relative URLs (same origin)
// In development, use REACT_APP_BACKEND_URL
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// Setup global axios interceptor for auto-refresh
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

axios.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      // Don't retry login or refresh requests
      if (originalRequest.url?.includes('/auth/login') || originalRequest.url?.includes('/auth/refresh')) {
        return Promise.reject(error);
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then(token => {
          originalRequest.headers['Authorization'] = `Bearer ${token}`;
          return axios(originalRequest);
        }).catch(err => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const storedToken = localStorage.getItem('token');
      if (!storedToken) {
        isRefreshing = false;
        return Promise.reject(error);
      }

      try {
        const { data } = await axios.post(`${API}/auth/refresh`, {}, {
          headers: { Authorization: `Bearer ${storedToken}` }
        });
        const newToken = data.token;
        localStorage.setItem('token', newToken);
        originalRequest.headers['Authorization'] = `Bearer ${newToken}`;
        processQueue(null, newToken);
        return axios(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        localStorage.removeItem('token');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [loading, setLoading] = useState(true);

  const verifyToken = useCallback(async () => {
    const storedToken = localStorage.getItem('token');
    if (!storedToken) {
      setLoading(false);
      return;
    }

    try {
      const response = await axios.get(`${API}/auth/verify`, {
        headers: { Authorization: `Bearer ${storedToken}` }
      });
      if (response.data.valid) {
        setUser({
          email: response.data.email,
          role: response.data.role || 'admin',
          name: response.data.name || '',
          user_id: response.data.user_id || '',
          pages: response.data.pages || [],
        });
        setToken(storedToken);

        // Proactive refresh: if token will expire in less than 7 days, refresh now
        try {
          const payload = JSON.parse(atob(storedToken.split('.')[1]));
          const expiresIn = (payload.exp * 1000) - Date.now();
          if (expiresIn < 7 * 24 * 3600 * 1000) {
            const refreshRes = await axios.post(`${API}/auth/refresh`, {}, {
              headers: { Authorization: `Bearer ${storedToken}` }
            });
            if (refreshRes.data.token) {
              localStorage.setItem('token', refreshRes.data.token);
              setToken(refreshRes.data.token);
            }
          }
        } catch (_) { /* ignore refresh errors during proactive check */ }
      }
    } catch (error) {
      localStorage.removeItem('token');
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    verifyToken();
  }, [verifyToken]);

  const login = async (email, password) => {
    const response = await axios.post(`${API}/auth/login`, { email, password });
    const { token: newToken, email: userEmail, role, name } = response.data;
    localStorage.setItem('token', newToken);
    setToken(newToken);
    let pages = [];
    try { pages = (await axios.get(`${API}/auth/verify`, { headers: { Authorization: `Bearer ${newToken}` } })).data.pages || []; } catch (_) { /* sem páginas */ }
    setUser({ email: userEmail, role: role || 'admin', name: name || '', user_id: response.data.user_id || '', pages });
    return response.data;
  };

  const logout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
  };

  const getAuthHeader = useCallback(() => {
    const currentToken = localStorage.getItem('token');
    return {
      headers: { Authorization: `Bearer ${currentToken}` }
    };
  }, []);

  const isAdmin = user?.role === 'admin';
  const isTechnician = user?.role === 'technician';
  const isInvisacook = user?.role === 'invisacook';

  return (
    <AuthContext.Provider value={{ user, token, login, logout, loading, getAuthHeader, isAdmin, isTechnician, isInvisacook }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;
