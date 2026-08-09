/**
 * UserProvider — citra-decks
 *
 * Not a port of Citra-UI's UserProvider.js (602 lines — org/dept scoping,
 * admin checks, credit balances, none of which apply here). This is a
 * minimal auth-state context wrapping the already-ported authService
 * singleton with exactly what the shell's LOADING/LANDING/LOGIN/APP state
 * machine needs: whether a session exists, whose, and how to set/clear it.
 */
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import authService from '../services/authService';

const UserContext = createContext(null);

export const useUser = () => {
  const context = useContext(UserContext);
  if (!context) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
};

const UserProvider = ({ children }) => {
  const [isInitialized, setIsInitialized] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userEmail, setUserEmail] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const hasToken = await authService.hasToken();
        if (cancelled) return;
        if (hasToken) {
          const email = await authService.getCurrentUserEmail().catch(() => null);
          setIsAuthenticated(true);
          setUserEmail(email);
        } else {
          setIsAuthenticated(false);
          setUserEmail(null);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
          setIsInitialized(true);
        }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Re-check auth whenever authService reports it needs a fresh login
  // (expired/invalid/missing token discovered mid-session).
  useEffect(() => {
    const unsubscribe = authService.onAuthRequired(() => {
      setIsAuthenticated(false);
      setUserEmail(null);
    });
    return unsubscribe;
  }, []);

  const handleAuthentication = useCallback(async ({ token, user }) => {
    await authService.setToken(token);
    setIsAuthenticated(true);
    setUserEmail(user?.email || null);
  }, []);

  const revalidateToken = useCallback(async () => {
    const isValid = await authService.validateToken();
    if (!isValid) {
      setIsAuthenticated(false);
      setUserEmail(null);
    }
    return isValid;
  }, []);

  const logout = useCallback(async () => {
    await authService.clearToken();
    setIsAuthenticated(false);
    setUserEmail(null);
  }, []);

  const contextValue = {
    isInitialized,
    isLoading,
    isAuthenticated,
    userEmail,
    handleAuthentication,
    revalidateToken,
    logout,
  };

  return (
    <UserContext.Provider value={contextValue}>
      {children}
    </UserContext.Provider>
  );
};

export default UserProvider;
