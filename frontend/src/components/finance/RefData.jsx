import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/components/finance/api";
import { useAuth } from "@/context/AuthContext";

const RefCtx = createContext(null);

export const RefDataProvider = ({ children }) => {
  const { isAdmin } = useAuth();
  const [categories, setCategories] = useState([]);
  const [techs, setTechs] = useState([]);

  const reload = useCallback(async () => {
    const c = await api.get("/finance/categories");
    setCategories(c.data);
    if (isAdmin) {
      const u = await api.get("/finance/techs");
      setTechs(u.data);
    }
  }, [isAdmin]);

  useEffect(() => {
    reload().catch(() => {});
  }, [reload]);

  const catById = Object.fromEntries(categories.map((c) => [c.id, c]));
  const techById = Object.fromEntries(techs.map((t) => [t.id, t]));

  return (
    <RefCtx.Provider value={{ categories, techs, catById, osById: {}, techById, reload }}>
      {children}
    </RefCtx.Provider>
  );
};

export const useRef_ = () => useContext(RefCtx);
