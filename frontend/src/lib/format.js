export const fmt = (n, currency = "AUD") =>
  new Intl.NumberFormat("en-AU", { style: "currency", currency, maximumFractionDigits: 0 }).format(n || 0);

export const fmt2 = (n, currency = "AUD") =>
  new Intl.NumberFormat("en-AU", { style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0);

export const fmtDate = (d) => {
  if (!d) return "—";
  const dt = new Date(d);
  if (isNaN(dt)) return d;
  return dt.toLocaleDateString("en-AU", { day: "2-digit", month: "short", year: "numeric" });
};

export const today = () => new Date().toISOString().slice(0, 10);

export const PARTNERS = ["Yash Sojitra", "Sanjay Jogani", "Pranay Jetani", "Max Ma"];
export const CURRENCIES = ["AUD", "USD", "INR"];
