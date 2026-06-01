import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes, useNavigate } from "react-router";
import { AdminShell } from "./routes/admin/AdminShell";
import { BinWidthEditor } from "./routes/admin/BinWidthEditor";
import { ConfirmationRoute } from "./routes/admin/ConfirmationScreen";
import { CubesGrid } from "./routes/admin/CubesGrid";
import { Diagnostics } from "./routes/admin/Diagnostics";
import { HistoryView } from "./routes/admin/HistoryView";
import Import from "./routes/admin/Import";
import { DevicesManager } from "./routes/admin/DevicesManager";
import { ProfilesManager } from "./routes/admin/ProfilesManager";
import { Settings } from "./routes/admin/Settings";
import { ShelfBinList } from "./routes/admin/ShelfBinList";
import { Wizard } from "./routes/admin/Wizard";
import { KioskView } from "./routes/kiosk/KioskView";
import { PairView } from "./routes/kiosk/PairView";
import { RevokeNotice } from "./routes/kiosk/DeviceLifecycle";
import { ProfilePicker } from "./routes/ProfilePicker";
import { RedeemPage } from "./routes/redeem/RedeemPage";
import { getSession } from "./api/session";
import { useSessionStore } from "./state/sessionStore";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

/**
 * App root — wraps with TanStack Query provider and react-router.
 *
 * Routes:
 *   /                           → KioskView (public, no auth)
 *   /select                     → ProfilePicker (browse-binding — no auth, D2-07)
 *   /admin                      → AdminShell (PIN gate on all /admin/* routes)
 *   /admin/settings             → Settings
 *   /admin/profiles             → ProfilesManager (profile list + status badges + drawer)
 *   /admin/cubes                → CubesGrid (list of shelves — SHELF A, SHELF B, …)
 *   /admin/cubes/:unit          → ShelfBinList (bin-card list for one shelf, sketch 002)
 *   /admin/cubes/:unit/:row/:col → BinWidthEditor (focused single-bin width editor, sketch 001)
 *   /admin/history              → HistoryView
 *   /admin/wizard               → Wizard (setup + reshuffle modes, D-01)
 *   /admin/wizard/done          → ConfirmationRoute (post-commit confirmation, D-15)
 *   /admin/import               → Import (stub — 07-05 replaces with real page)
 *   /admin/diagnostics          → Diagnostics (OBS-05/06/07 — phase 08-04)
 *   /redeem/:code               → RedeemPage (public member invite redemption — Phase 7 / AUTH-02)
 *
 * Design tokens are imported in main.tsx (single entry point).
 */

/**
 * AppInner — rendered inside BrowserRouter so useNavigate is available.
 *
 * Bootstrap (D2-08, Pattern 6): on mount, fetch GET /api/session and update
 * the session store. If the response has no bound_profile_id (unbound), redirect
 * to /select. Single-profile auto-bind is handled server-side — the SPA only
 * redirects when truly unbound after the server has had its chance to auto-bind.
 *
 * Phase 6 (06-02 / D-06): global terminal-revoke handler.
 * Subscribes to revokePending from sessionStore. When it becomes true (from either
 * SSE device_revoked or a 403 device_revoked from any in-flight call), shows the
 * RevokeNotice overlay, then after ~2.5s calls clearBoundProfile() (nulls
 * boundProfileId → KioskView SSE cleanup closes the old EventSource, D-07),
 * navigates to /pair, and calls resetRevoke() so a future re-pair can revoke again.
 * This is the SINGLE terminal-revoke handler — it runs at App level, not inside
 * KioskView, so it fires even if KioskView is not mounted (D-06).
 */
function AppInner() {
  const navigate = useNavigate();
  const setSession = useSessionStore((s) => s.setSession);
  const revokePending = useSessionStore((s) => s.revokePending);
  const clearBoundProfile = useSessionStore((s) => s.clearBoundProfile);
  const resetRevoke = useSessionStore((s) => s.resetRevoke);

  // Session bootstrap effect
  useEffect(() => {
    getSession()
      .then((data) => {
        setSession(data);
        const currentPath = window.location.pathname;

        // D3-03: if the device fingerprint is already paired (03-03 session extension),
        // stay on '/' — the paired device should go straight to the bound-profile search UI.
        // Never redirect /pair or /admin to '/' — those are intentional destinations.
        if (data.is_device_paired && data.bound_profile_id) {
          if (currentPath !== "/" && !currentPath.startsWith("/admin")) {
            void navigate("/", { replace: true });
          }
          return;
        }

        // D2-08: if no bound_profile_id, the SPA must go to /select.
        // Single-profile auto-bind is server-side — server sets the cookie and
        // returns bound_profile_id in the same response, so we only redirect here
        // when the response genuinely has no binding.
        // Exemption: /pair and /redeem/* are always allowed (pairing + invite redemption flows).
        if (
          !data.bound_profile_id &&
          currentPath !== "/pair" &&
          !currentPath.startsWith("/admin") &&
          !currentPath.startsWith("/redeem")
        ) {
          void navigate("/select", { replace: true });
        }
      })
      .catch(() => {
        // Degrade gracefully — stay on current route (offline / server down).
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Global terminal-revoke handler (D-06, T-06-06).
  // Runs at App level — mount-independent of KioskView.
  // Fires from SSE device_revoked event AND 403 device_revoked intercept in client.ts;
  // triggerRevoke() is idempotent so whichever arrives first wins — one notice, one navigation.
  useEffect(() => {
    if (!revokePending) return;

    const timer = setTimeout(() => {
      // clearBoundProfile() nulls boundProfileId → KioskView SSE effect cleanup
      // closes the old EventSource (the effect's return() => es.close() path, D-07).
      clearBoundProfile();
      void navigate("/pair", { replace: true });
      resetRevoke();
    }, 2500);

    return () => clearTimeout(timer);
  }, [revokePending, clearBoundProfile, navigate, resetRevoke]);

  return (
    <>
      {/* Terminal-revoke overlay — rendered above all routes (D-06) */}
      {revokePending && <RevokeNotice />}
      <Routes>
        <Route path="/" element={<KioskView />} />
        <Route path="/pair" element={<PairView />} />
        <Route path="/select" element={<ProfilePicker />} />
        <Route path="/redeem/:code" element={<RedeemPage />} />
        <Route path="/admin" element={<AdminShell />}>
          <Route index element={<Settings />} />
          <Route path="settings" element={<Settings />} />
          <Route path="profiles" element={<ProfilesManager />} />
          <Route path="devices" element={<DevicesManager />} />
          <Route path="cubes" element={<CubesGrid />} />
          <Route path="cubes/:unit" element={<ShelfBinList />} />
          <Route path="cubes/:unit/:row/:col" element={<BinWidthEditor />} />
          <Route path="history" element={<HistoryView />} />
          <Route path="wizard" element={<Wizard />} />
          <Route path="wizard/done" element={<ConfirmationRoute />} />
          <Route path="import" element={<Import />} />
          <Route path="diagnostics" element={<Diagnostics />} />
        </Route>
      </Routes>
    </>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppInner />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
