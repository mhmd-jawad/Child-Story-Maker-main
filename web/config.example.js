window.APP_CONFIG = {
  apiBase:
    window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
      ? ""
      : "/api",
  supabaseUrl: "https://your-project.supabase.co",
  supabaseAnonKey: "your-anon-key"
};
