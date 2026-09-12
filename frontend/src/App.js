import { useEffect, useRef, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import { Toaster } from "./components/ui/sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { api } from "./lib/api";
import { Card, CardContent } from "./components/ui/card";
import { Button } from "./components/ui/button";
import { ShieldCheck } from "lucide-react";
import Layout from "./components/Layout";
import Cursor from "./components/Cursor";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Projects from "./pages/Projects";
import ProjectDetail from "./pages/ProjectDetail";
import Partners from "./pages/Partners";
import Investments from "./pages/Investments";
import Properties from "./pages/Properties";
import Feasibility from "./pages/Feasibility";
import Admin from "./pages/Admin";
import "./App.css";

function Protected({ children }) {
  const { user, loading, pending } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="font-mono text-sm text-muted-foreground" data-testid="auth-loading">Loading…</p>
      </div>
    );
  }
  if (pending) return <PendingApproval />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function PendingApproval() {
  const { logout } = useAuth();
  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-sm text-center">
        <CardContent className="p-8 space-y-4">
          <ShieldCheck className="h-10 w-10 mx-auto text-gold" />
          <h1 className="font-heading font-bold text-xl" data-testid="pending-title">Awaiting Approval</h1>
          <p className="text-sm text-muted-foreground">
            Your account is pending approval. Yash will review your request and grant access shortly.
          </p>
          <Button variant="outline" data-testid="pending-logout-button" onClick={logout}>Sign out</Button>
        </CardContent>
      </Card>
    </div>
  );
}

function AuthCallback() {
  const navigate = useNavigate();
  const { setUser, setPending } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;
    const sessionId = window.location.hash.split("session_id=")[1]?.split("&")[0];
    api.post("/auth/google/session", { session_id: sessionId })
      .then((r) => {
        window.history.replaceState(null, "", window.location.pathname);
        if (r.data.status === "approved") {
          setUser(r.data);
          navigate("/", { replace: true, state: { user: r.data } });
        } else {
          setPending(true);
          navigate("/", { replace: true });
        }
      })
      .catch(() => navigate("/login", { replace: true }));
  }, []);

  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <p className="font-mono text-sm text-muted-foreground" data-testid="auth-callback-loading">Signing you in…</p>
    </div>
  );
}

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/:id" element={<ProjectDetail />} />
        <Route path="/partners" element={<Partners />} />
        <Route path="/investments" element={<Investments />} />
        <Route path="/properties" element={<Properties />} />
        <Route path="/feasibility" element={<Feasibility />} />
        <Route path="/admin" element={<Admin />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <AuthProvider>
        <Cursor />
        <BrowserRouter>
          <AppRouter />
        </BrowserRouter>
        <Toaster richColors position="top-right" />
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
