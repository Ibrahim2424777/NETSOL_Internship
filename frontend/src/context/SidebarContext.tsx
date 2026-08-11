import { createContext, useContext, useState } from 'react';
import type { ReactNode } from 'react';

// Two independent booleans for two independent behaviors: `showSidebar` is
// the mobile drawer's open/closed state (Offcanvas), `sidebarCollapsed` is
// the desktop-only collapse-to-width-0 state. Only one of the two has any
// visual effect at a given viewport width, so toggleSidebar can safely flip
// both at once without checking screen size.
//
// Lives at AppLayout level (provided once, above both the header's toggle
// button and ChatPage's sidebar) so the header can control the sidebar
// without the two being in a parent/child relationship.
interface SidebarContextValue {
  showSidebar: boolean;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  closeMobileSidebar: () => void;
}

const SidebarContext = createContext<SidebarContextValue | null>(null);

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [showSidebar, setShowSidebar] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const value: SidebarContextValue = {
    showSidebar,
    sidebarCollapsed,
    toggleSidebar: () => {
      setShowSidebar((s) => !s);
      setSidebarCollapsed((c) => !c);
    },
    closeMobileSidebar: () => setShowSidebar(false),
  };

  return <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>;
}

export function useSidebar(): SidebarContextValue {
  const ctx = useContext(SidebarContext);
  if (!ctx) throw new Error('useSidebar must be used within a SidebarProvider');
  return ctx;
}
